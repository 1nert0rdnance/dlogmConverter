import os, sys, subprocess, time, threading, ctypes, tempfile, re
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ANSI Color and Screen Control Codes
RESET       = "\033[0m"
BOLD        = "\033[1m"
DIM         = "\033[2m"
RED         = "\033[91m"
GREEN       = "\033[92m"
YELLOW      = "\033[93m"
CYAN        = "\033[96m"
WHITE       = "\033[97m"
GRAY        = "\033[90m"

SAVE_CURSOR    = "\033[s"
RESTORE_CURSOR = "\033[u"
HIDE_CURSOR    = "\033[?25l"
SHOW_CURSOR    = "\033[?25h"

# Global states to track rendering metrics and handle dynamic window resizing
LOG_HISTORY = []
LAST_W = 0
LAST_H = 0
ANSI_REGEX = re.compile(r'\033\[[0-9;]*[a-zA-Z]')

def enable_ansi():
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def term_size():
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24

def strip_ansi(s):
    return ANSI_REGEX.sub('', s)

def log_print(msg):
    """Tracks stdout logs in a history buffer so they can be re-rendered cleanly on resize."""
    LOG_HISTORY.append(msg)
    print(msg)

def human_size(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def human_time(s):
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    elif m:
        return f"{m}m {s:02d}s"
    return f"{s}s"

def get_ffmpeg_version():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        first_line = r.stdout.splitlines()[0]
        parts = first_line.split("version ")
        if len(parts) > 1:
            return parts[1].split()[0]
        return "unknown"
    except Exception:
        return "unknown"

def get_duration_secs(filepath):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return None

def read_progress(path):
    data = {}
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, _, v = line.partition("=")
                    data[k.strip()] = v.strip()
    except Exception:
        pass
    return data

def get_ratio_color(ratio):
    if ratio < 1.0:
        return GREEN
    elif ratio <= 1.5:
        return YELLOW
    return RED

def prompt_codec():
    os.system('cls' if sys.platform == 'win32' else 'clear')
    w, _ = term_size()
    w = min(w, 100)
    rule = GRAY + "─" * w + RESET

    print(f"\n  {BOLD}{WHITE}LUT CONVERTER{RESET}\n")
    print(rule)
    print(f"\n  {GRAY}Select output codec:{RESET}\n")
    print(f"  {CYAN}[1]{RESET}  {BOLD}H.264{RESET}  {GRAY}— faster encode, universal compatibility{RESET}")
    print(f"       {GRAY}CRF 18, yuv420p, preset fast{RESET}")
    print()
    print(f"  {CYAN}[2]{RESET}  {BOLD}H.265{RESET}  {GRAY}— smaller files (~40%), plays on most modern devices{RESET}")
    print(f"       {GRAY}CRF 24, yuv420p, preset fast{RESET}")
    print()
    print(f"  {CYAN}[3]{RESET}  {BOLD}AV1 Next-Gen Archive{RESET}  {GRAY}— highest space savings, ideal for deep storage{RESET}")
    print(f"       {GRAY}CRF 26, yuv420p, cpu-used 6 (libaom-av1){RESET}")
    print(f"\n{rule}\n")

    while True:
        choice = input("  Enter 1, 2, or 3: ").strip()
        if choice == "1":
            return "h264"
        elif choice == "2":
            return "h265"
        elif choice == "3":
            return "av1"
        else:
            print(f"  {RED}Please enter 1, 2, or 3.{RESET}")

def setup_scroll_regions(footer_height):
    w, h = term_size()
    scroll_bottom = max(1, h - footer_height)
    sys.stdout.write(f"\033[1;{scroll_bottom}r")
    sys.stdout.write(f"\033[{scroll_bottom};1H")
    sys.stdout.flush()

def reset_scroll_regions():
    sys.stdout.write("\033[r")
    sys.stdout.write(SHOW_CURSOR)
    sys.stdout.flush()

def check_and_handle_resize(footer_height):
    """Detects layout resizing. Wipes screen artifacts and shifts layout seamlessly."""
    global LAST_W, LAST_H
    w, h = term_size()
    if w == LAST_W and h == LAST_H:
        return False

    LAST_W, LAST_H = w, h
    
    # Reset scroll region completely to allow deep cleaning
    sys.stdout.write("\033[r")
    sys.stdout.write("\033[2J\033[H")
    
    # Reprint history logs that fit inside the shifting upper grid
    max_logs = h - footer_height - 1
    if max_logs > 0:
        visible_logs = LOG_HISTORY[-max_logs:]
        for line in visible_logs:
            sys.stdout.write(line + "\n")
            
    # Re-apply scroll boundaries matching new size coordinates
    scroll_bottom = max(1, h - footer_height)
    sys.stdout.write(f"\033[1;{scroll_bottom}r")
    sys.stdout.write(f"\033[{scroll_bottom};1H")
    sys.stdout.flush()
    return True

def format_box_line(content_left, content_right="", width=80):
    """Pads space internally so side-panel box layout lines line up perfectly."""
    inner_w = width - 4  # accounted for borders '│ ' and ' │'
    left_len = len(strip_ansi(content_left))
    right_len = len(strip_ansi(content_right))
    space_needed = inner_w - left_len - right_len
    if space_needed < 0:
        return f"{GRAY}│ {RESET}{content_left} {content_right}{GRAY} │{RESET}"
    return f"{GRAY}│ {RESET}{content_left}{' ' * space_needed}{content_right}{GRAY} │{RESET}"

def draw_sticky_footer(
    lut_name, ffmpeg_ver, codec, current_file, current_idx, total,
    elapsed, fps, speed, bitrate, current_out_time, duration,
    cpu_pct, mem_pct, footer_height=7
):
    w, h = term_size()
    w = min(w, 100)
    
    lines = []
    def make_progress_bar(fraction, bar_w=24):
        f = max(0.0, min(1.0, fraction))
        filled = int(f * bar_w)
        empty = bar_w - filled
        return f"{GREEN}{'█' * filled}{GRAY}{'░' * empty}{RESET}"

    if codec == "h264":
        codec_label = "H.264"
    elif codec == "h265":
        codec_label = "H.265"
    else:
        codec_label = "AV1"

    file_frac = (current_out_time / duration) if (current_file and duration) else 0.0

    # Line 1: Top Border
    lines.append(GRAY + "┌" + "─" * (w - 2) + "┐" + RESET)
    
    # Line 2: Header Info
    left_title = f"{BOLD}{WHITE}LUT CONVERTER{RESET}  {GRAY}·  ffmpeg v{ffmpeg_ver}  ·  {lut_name}{RESET}"
    right_title = f"{GRAY}Codec: {RESET}{CYAN}{codec_label}{RESET}"
    lines.append(format_box_line(left_title, right_title, w))
    
    # Line 3: Divider
    lines.append(GRAY + "├" + "─" * (w - 2) + "┤" + RESET)
    
    # Line 4: Current Processing File Bar
    if current_file:
        pct = int(file_frac * 100)
        ct = human_time(current_out_time) if current_out_time else "0s"
        dt = human_time(duration) if duration else "?"
        pbar = make_progress_bar(file_frac, bar_w=26)
        left_file = f"{WHITE}RUNNING{RESET} : {CYAN}{Path(current_file).name}{RESET}"
        right_file = f"[{pbar}] {CYAN}{pct}%{RESET} {GRAY}({ct}/{dt}){RESET}"
    else:
        left_file = f"{GRAY}No active encoding job...{RESET}"
        right_file = ""
    lines.append(format_box_line(left_file, right_file, w))
    
    # Line 5: System Performance Core Metrics
    fps_s = f"{GRAY}fps {RESET}{CYAN}{fps:.1f}{RESET}" if fps else f"{GRAY}fps {RESET}—"
    spd_s = f"{GRAY}speed {RESET}{CYAN}{speed:.2f}x{RESET}" if speed else f"{GRAY}speed {RESET}—"
    bit_s = f"{GRAY}bitrate {RESET}{CYAN}{bitrate/1000:.1f} Mbps{RESET}" if bitrate else f"{GRAY}bitrate {RESET}—"
    sys_stats = ""
    if HAS_PSUTIL and cpu_pct is not None:
        cpu_color = RED if cpu_pct > 85 else YELLOW if cpu_pct > 60 else CYAN
        sys_stats = f"  ·  {GRAY}cpu {RESET}{cpu_color}{cpu_pct:.0f}%{RESET}  ·  {GRAY}ram {RESET}{CYAN}{mem_pct:.0f}%{RESET}"
    lines.append(format_box_line(f"{WHITE}STATS{RESET}   : {fps_s}  ·  {spd_s}  ·  {bit_s}{sys_stats}", "", w))
    
    # Line 6: Global Batch Progress Panel
    global_frac = ((current_idx - 1) + file_frac) / total
    g_pct = int(global_frac * 100)
    g_pbar = make_progress_bar(global_frac, bar_w=26)
    left_global = f"{WHITE}GLOBAL{RESET}  : {CYAN}{current_idx - 1}/{total}{RESET} Files Processed"
    right_global = f"[{g_pbar}] {CYAN}{g_pct}%{RESET}  ·  {GRAY}Elapsed: {CYAN}{human_time(elapsed)}{RESET}"
    lines.append(format_box_line(left_global, right_global, w))
    
    # Line 7: Bottom Border Frame Cap
    lines.append(GRAY + "└" + "─" * (w - 2) + "┘" + RESET)

    # Output to stdout safely via position tracking offsets
    draw_str = SAVE_CURSOR
    start_row = h - footer_height + 1
    for i, line in enumerate(lines):
        draw_str += f"\033[{start_row + i};1H\033[K{line}"
    draw_str += RESTORE_CURSOR
    
    sys.stdout.write(draw_str)
    sys.stdout.flush()

def main():
    enable_ansi()
    script_dir = Path(sys.argv[0]).parent.resolve()
    os.chdir(script_dir)

    cube_files = list(script_dir.glob("*.cube"))
    if not cube_files:
        print(f"{RED}No .cube LUT file found in {script_dir}{RESET}")
        sys.exit(1)
    lut_file = cube_files[0]

    seen = set()
    mp4_files = []
    for f in sorted(script_dir.iterdir()):
        if f.is_file() and f.suffix.lower() == ".mp4" and f.name.lower() not in seen:
            seen.add(f.name.lower())
            mp4_files.append(f)
    if not mp4_files:
        print(f"{RED}No .MP4 files found in {script_dir}{RESET}")
        sys.exit(1)

    output_dir = script_dir / "processed"
    output_dir.mkdir(exist_ok=True)

    codec = prompt_codec()
    ffmpeg_ver = get_ffmpeg_version()

    all_files   = [str(f) for f in mp4_files]
    total       = len(all_files)
    done_files  = []
    error_files = [] # Now stores tuples of (filepath, error_message)
    file_summary_data = []

    cpu_pct = mem_pct = None
    stop_monitor = threading.Event()

    def resource_monitor():
        nonlocal cpu_pct, mem_pct
        while not stop_monitor.is_set():
            try:
                cpu_pct = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                mem_pct = mem.percent
            except Exception:
                pass
            time.sleep(0.5)

    if HAS_PSUTIL:
        t = threading.Thread(target=resource_monitor, daemon=True)
        t.start()

    # Enter structural scrolling isolated panel grid layout mode
    FOOTER_HEIGHT = 7
    os.system('cls' if sys.platform == 'win32' else 'clear')
    
    global LAST_W, LAST_H
    LAST_W, LAST_H = term_size()
    
    sys.stdout.write(HIDE_CURSOR)
    setup_scroll_regions(FOOTER_HEIGHT)

    timestamp = time.strftime("%H:%M:%S")
    log_print(f"{GRAY}[{timestamp}]{RESET} {GREEN}STARTING BATCH:{RESET} {total} files queued.")

    batch_start = time.time()

    for idx, src in enumerate(all_files, start=1):
        src_path    = Path(src)
        out_path    = output_dir / src_path.name
        source_size = src_path.stat().st_size if src_path.exists() else 0
        duration    = get_duration_secs(src)

        progress_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
        progress_path = progress_file.name
        progress_file.close()

        timestamp = time.strftime("%H:%M:%S")
        log_print(f"{GRAY}[{timestamp}]{RESET} {WHITE}ENCODING{RESET} : {src_path.name} ...")

        if codec == "av1":
            codec_args = ["-c:v", "libaom-av1", "-cpu-used", "6", "-row-mt", "1", "-crf", "26", "-pix_fmt", "yuv420p"]
        elif codec == "h265":
            codec_args = ["-c:v", "libx265", "-preset", "fast", "-crf", "24", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
        else:
            codec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]

        cmd = [
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error",
            "-i", str(src_path),
            "-vf", f"lut3d='{lut_file.name}',format=yuv420p",
            *codec_args,
            "-map_metadata", "0",
            "-c:a", "copy",
            "-progress", progress_path,
            "-nostats",
            str(out_path)
        ]

        # Dedicated log file for capturing FFmpeg crashes natively
        error_log_path = progress_path + ".err"

        with open(error_log_path, "w") as err_f:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)

            fps = speed = bitrate = None
            current_out_time = 0.0

            try:
                while proc.poll() is None:
                    # Dynamic event layout resize trigger check
                    check_and_handle_resize(FOOTER_HEIGHT)

                    data = read_progress(progress_path)

                    out_time_us = data.get("out_time_us") or data.get("out_time_ms")
                    if out_time_us:
                        try: current_out_time = float(out_time_us) / 1_000_000
                        except Exception: pass

                    fps_val = data.get("fps")
                    if fps_val and fps_val != "0":
                        try: fps = float(fps_val)
                        except Exception: pass

                    speed_val = data.get("speed", "").replace("x", "")
                    if speed_val and "not a number" not in speed_val:
                        try: speed = float(speed_val)
                        except Exception: pass

                    bitrate_val = data.get("bitrate", "").replace("kbits/s", "")
                    if bitrate_val and "N/A" not in bitrate_val:
                        try: bitrate = float(bitrate_val)
                        except Exception: pass

                    elapsed = time.time() - batch_start

                    draw_sticky_footer(
                        lut_name=lut_file.name, ffmpeg_ver=ffmpeg_ver, codec=codec,
                        current_file=src, current_idx=idx, total=total, elapsed=elapsed,
                        fps=fps, speed=speed, bitrate=bitrate, current_out_time=current_out_time,
                        duration=duration, cpu_pct=cpu_pct, mem_pct=mem_pct,
                        footer_height=FOOTER_HEIGHT
                    )
                    time.sleep(0.25)
            finally:
                try: os.unlink(progress_path)
                except Exception: pass

        ret = proc.returncode
        out_size_final = out_path.stat().st_size if out_path.exists() else 0
        timestamp = time.strftime("%H:%M:%S")

        # Double check sizing right at the file logging swap frame boundary
        check_and_handle_resize(FOOTER_HEIGHT)

        if ret == 0:
            done_files.append(src)
            ratio = out_size_final / source_size if source_size else 1.0
            r_color = get_ratio_color(ratio)
            log_print(f"{GRAY}[{timestamp}]{RESET} {GREEN}SUCCESS{RESET}  : {src_path.name} "
                      f"({human_size(source_size)} -> {human_size(out_size_final)}, {r_color}{ratio:.2f}x ratio{RESET})")
            file_summary_data.append((src_path.name, source_size, out_size_final, True))
            try: os.unlink(error_log_path)
            except Exception: pass
        else:
            err_msg = ""
            try:
                with open(error_log_path, "r") as err_f:
                    err_msg = err_f.read().strip()
                os.unlink(error_log_path)
            except Exception:
                pass
            
            error_files.append((src, err_msg))
            log_print(f"{GRAY}[{timestamp}]{RESET} {RED}FAILED{RESET}   : {src_path.name}")
            file_summary_data.append((src_path.name, source_size, 0, False))

    stop_monitor.set()
    reset_scroll_regions()

    # Final summary execution breakdown matrix report
    print(f"\n  {BOLD}{GREEN}All done!{RESET}  {len(done_files)}/{total} files processed successfully.")
    print(f"  Output folder: {output_dir}\n")

    if file_summary_data:
        print(f"  {'File':<36} {'Source':>10} {'Output':>10} {'Ratio':>8}")
        print("  " + "─" * 68)
        for name, src_sz, out_sz, success in file_summary_data:
            if success:
                ratio = out_sz / src_sz if src_sz else 1.0
                color = get_ratio_color(ratio)
                print(f"  {name:<36} {human_size(src_sz):>10} {human_size(out_sz):>10} {color}{ratio:.2f}x{RESET}")
            else:
                print(f"  {RED}{name:<36} {'—':>10} {'—':>10} {'ERROR':>8}{RESET}")
        print()

    # Detailed Error Reporting Dump
    if error_files:
        print(f"  {RED}Failed files:{RESET}")
        for ef_path, ef_err in error_files:
            print(f"  {RED}  ✗ {Path(ef_path).name}{RESET}")
            if ef_err:
                err_lines = [line.strip() for line in ef_err.split('\n') if line.strip()]
                if err_lines:
                    print(f"      {GRAY}Reason: {err_lines[-1]}{RESET}")
        print()

    input("  Press Enter to exit.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        reset_scroll_regions()
        print(f"\n{RED}Batch process aborted by user.{RESET}")