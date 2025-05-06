#!/usr/bin/env python3
import subprocess
import threading
import argparse
import sys
import re
import time

#test
# Regular expression to parse iperf3 UDP interval output.
# Expected format (example):
# [  5]   0.00-10.00 sec  7.65 MBytes  6.41 Mbits/sec  0.089 ms  0/555 (0%)
interval_regex = re.compile(
    r'^\[\s*\d+\]\s+(?P<interval>[\d\.]+-[\d\.]+)\s+sec\s+'
    r'(?P<transfer>[\d\.]+\s+\S+)\s+(?P<bandwidth>[\d\.]+\s+\S+)\s+'
    r'(?P<jitter>[\d\.]+)\s+ms\s+(?P<lost>\d+)/(?P<total>\d+)\s+\((?P<loss_percent>\d+)%\)'
)

# Shared dictionary to hold the latest stats for each test.
results = {
    "voice_forward": {},
    "voice_reverse": {},
    "bg_forward": {},
    "bg_reverse": {}
}

def run_udp_test_continuous(server, port, duration, bandwidth, packet_size, test_name, dscp=None, reverse=False):
    """
    Runs an iperf3 UDP test in non-JSON mode with a 10-second reporting interval.
    Reads output line-by-line and updates the shared results dictionary for test_name.
    """
    # Prepend "stdbuf -oL" to force line buffering.
    cmd = [
        "stdbuf", "-oL", "iperf3",
        "-c", server,
        "-p", str(port),
        "-u",
        "-t", str(duration),
        "-i", "10",   # reporting interval of 10 seconds
        "-b", bandwidth,
        "-l", str(packet_size)
    ]
    if dscp is not None:
        cmd += ["-S", str(dscp)]
    if reverse:
        cmd.append("-R")
    
    print(f"Starting UDP test for {test_name}: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
    except Exception as e:
        print(f"Failed to start iperf3 for {test_name}: {e}", file=sys.stderr)
        return

    # Read output line by line.
    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        # Uncomment below for full debug of each output line:
        # print(f"[{test_name}] {line}")
        m = interval_regex.match(line)
        if m:
            try:
                jitter = float(m.group("jitter"))
                lost = int(m.group("lost"))
                total = int(m.group("total"))
                loss_percent = int(m.group("loss_percent"))
                results[test_name] = {
                    "jitter": jitter,
                    "lost": lost,
                    "total": total,
                    "loss_percent": loss_percent,
                    "interval": m.group("interval")
                }
            except Exception as e:
                print(f"Error parsing line in {test_name}: {line}  Error: {e}", file=sys.stderr)
    process.wait()
    results[test_name]["done"] = True

def main():
    parser = argparse.ArgumentParser(
        description="Bidirectional UDP QoS Test with periodic reporting every 10 seconds."
    )
    parser.add_argument("-s", "--server", required=True, help="iperf3 server address (IP or hostname)")
    parser.add_argument("-t", "--duration", type=int, default=60, help="Test duration in seconds")
    
    # Voice UDP test parameters.
    parser.add_argument("--voice_bandwidth", default="64k", help="Bandwidth for voice UDP test (e.g., '64k')")
    parser.add_argument("--voice_packet_size", default="160", help="Packet size for voice UDP test in bytes (default: 160)")
    parser.add_argument("--voice_forward_port", type=int, default=5201, help="Server port for voice forward test (default: 5201)")
    parser.add_argument("--voice_reverse_port", type=int, default=5202, help="Server port for voice reverse test (default: 5202)")
    
    # Background UDP test parameters.
    parser.add_argument("--bg_bandwidth", default="100M", help="Bandwidth for background UDP test (e.g., '100M')")
    parser.add_argument("--bg_packet_size", default="1400", help="Packet size for background UDP test in bytes (default: 1400)")
    parser.add_argument("--bg_forward_port", type=int, default=5203, help="Server port for background forward test (default: 5203)")
    parser.add_argument("--bg_reverse_port", type=int, default=5204, help="Server port for background reverse test (default: 5204)")
    
    args = parser.parse_args()

    threads = []
    thread_voice_forward = threading.Thread(
        target=run_udp_test_continuous,
        args=(args.server, args.voice_forward_port, args.duration, args.voice_bandwidth,
              args.voice_packet_size, "voice_forward", 184, False)
    )
    threads.append(thread_voice_forward)
    
    thread_voice_reverse = threading.Thread(
        target=run_udp_test_continuous,
        args=(args.server, args.voice_reverse_port, args.duration, args.voice_bandwidth,
              args.voice_packet_size, "voice_reverse", 184, True)
    )
    threads.append(thread_voice_reverse)
    
    thread_bg_forward = threading.Thread(
        target=run_udp_test_continuous,
        args=(args.server, args.bg_forward_port, args.duration, args.bg_bandwidth,
              args.bg_packet_size, "bg_forward", None, False)
    )
    threads.append(thread_bg_forward)
    
    thread_bg_reverse = threading.Thread(
        target=run_udp_test_continuous,
        args=(args.server, args.bg_reverse_port, args.duration, args.bg_bandwidth,
              args.bg_packet_size, "bg_reverse", None, True)
    )
    threads.append(thread_bg_reverse)
    
    for thread in threads:
        thread.start()

    start_time = time.time()
    while any(thread.is_alive() for thread in threads):
        time_elapsed = int(time.time() - start_time)
        print(f"\n--- Report at {time_elapsed} seconds ---")
        for test_name in ["voice_forward", "voice_reverse", "bg_forward", "bg_reverse"]:
            stats = results.get(test_name, {})
            if stats:
                jitter = stats.get("jitter", "N/A")
                lost = stats.get("lost", "N/A")
                total = stats.get("total", "N/A")
                loss_percent = stats.get("loss_percent", "N/A")
                interval = stats.get("interval", "")
                print(f"{test_name.replace('_', ' ').title()}: Interval {interval} sec, "
                      f"Jitter: {jitter} ms, Lost: {lost} / {total}, Loss%: {loss_percent}%")
            else:
                print(f"{test_name.replace('_', ' ').title()}: No data yet.")
        time.sleep(10)

    for thread in threads:
        thread.join()

    print("\n--- Final Results ---")
    for test_name in ["voice_forward", "voice_reverse", "bg_forward", "bg_reverse"]:
        stats = results.get(test_name, {})
        if stats:
            jitter = stats.get("jitter", "N/A")
            lost = stats.get("lost", "N/A")
            total = stats.get("total", "N/A")
            loss_percent = stats.get("loss_percent", "N/A")
            interval = stats.get("interval", "")
            print(f"{test_name.replace('_', ' ').title()}: Interval {interval} sec, "
                  f"Jitter: {jitter} ms, Lost: {lost} / {total}, Loss%: {loss_percent}%")
        else:
            print(f"{test_name.replace('_', ' ').title()}: No data available.")

if __name__ == "__main__":
    main()
