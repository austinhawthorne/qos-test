# On the server, start:
iperf3 -s -p 5201  &  # voice forward
iperf3 -s -p 5202  &  # voice reverse
iperf3 -s -p 5203  &  # background forward
iperf3 -s -p 5204  &  # background reverse
