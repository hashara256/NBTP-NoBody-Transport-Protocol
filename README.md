# NoBody Transport Protocol (NBTP)

**NBTP** is a proof-of-concept transport protocol designed to transmit data via **IPv6 addresses**, embedding the data directly into the address and removing traditional payloads. This makes NBTP particularly useful for **circumventing censorship and network restrictions**, as it eliminates the visible packet body that traditional VPNs and communication protocols rely on. NBTP supports **TCP**, **UDP**, and **raw socket** transmissions, allowing it to function for various applications, including secure communications.

This project includes a Python implementation, with plans for a future Go version.

## Features

- **IPv6 Address-Based Transmission**: Encodes data directly into IPv6 addresses, removing the traditional packet body and making it difficult for censorship systems or firewalls to detect.
- **Supports Multiple Protocols**: Capable of transmitting TCP, UDP, and raw socket data, making it versatile for different use cases.
- **Reliable Transmission**: Implements an ACK/NACK system to ensure packet delivery and handle retransmissions.
- **Out-of-Order Packet Handling**: Buffers and reorders out-of-sequence packets to maintain the integrity of tunneled connections.
- **Congestion Control**: Implements congestion control similar to TCP, using a dynamic congestion window (`cwnd`) to avoid overwhelming the network.
- **Flow Control**: Limits the number of unacknowledged packets using the congestion window (`cwnd`), ensuring smoother handling of multiple clients.
- **Multi-Client Support**: Handles multiple concurrent clients using a thread pool to efficiently manage resources.

## How It Works

NBTP operates by embedding data within IPv6 addresses, bypassing the need for traditional packet bodies. This approach makes it harder for censorship mechanisms, deep packet inspection (DPI) systems, or firewalls to detect and block communication. By transmitting data within the IPv6 address itself, NBTP can effectively bypass restrictions that target protocols like VPNs, SSH, or typical TCP/UDP traffic.

### 1. **Client**:
    - Converts **TCP**, **UDP**, or **raw socket** packets into NBTP packets by encoding the data into IPv6 addresses.
    - Uses an ACK/NACK system to ensure reliable delivery, with built-in flow and congestion control mechanisms to avoid overwhelming the server.
    - Implements a congestion window (`cwnd`) to limit how many unacknowledged packets can be in flight at any time.

### 2. **Server**:
    - Receives NBTP packets, decodes the data, and forwards it to the appropriate destination (e.g., an SSH server for TCP, or UDP-based services).
    - Tracks expected sequence numbers for each client and handles out-of-order packets using a buffer.
    - Sends ACKs for successfully received packets and NACKs for lost packets, prompting the client to retransmit.

## Circumventing Network Blockades

NBTP is particularly useful in **bypassing censorship and firewall restrictions** that block VPN traffic. Since NBTP **transmits data without a traditional payload** and encodes it within IPv6 addresses, it is difficult for firewalls, deep packet inspection (DPI), and other network filters to detect and block the communication. This makes NBTP a powerful tool in environments where traditional VPNs, SSH tunnels, or standard internet traffic are blocked or heavily scrutinized.

### Example Use Cases:

- **Bypass VPN Blockades**: Use NBTP to bypass firewalls or censorship that block VPN traffic, since NBTP packets have no detectable body.
- **Circumvent Deep Packet Inspection (DPI)**: NBTP can evade DPI-based censorship mechanisms because the data is embedded within the IPv6 address itself, not the packet body.
- **Censorship-Resistant Communications**: NBTP provides a novel method for ensuring communication can proceed even in restrictive environments, such as countries with heavy internet censorship.

## Congestion Control

NBTP incorporates a **congestion control algorithm** inspired by TCP, which adjusts the sending rate based on network conditions:

- **Slow Start**: The client begins with a small congestion window (`cwnd`) and increases it exponentially with each successful acknowledgment until it hits the slow start threshold (`ssthresh`).
- **Congestion Avoidance**: After the threshold is reached, the window increases linearly to avoid network congestion.
- **Congestion Detection**: When packet loss is detected (via NACK or timeout), the client reduces `cwnd` and enters slow start again.

### Example

The client initially starts with a `cwnd` of 1. As ACKs are received, `cwnd` increases until a packet is lost. At that point, the client halves its sending rate (`ssthresh`) and re-enters slow start.

## Protocol Compatibility

NBTP is designed to handle multiple types of traffic, making it flexible for different use cases:
- **TCP**: For reliable, connection-based traffic such as SSH.
- **UDP**: For connectionless, fast transmission protocols like DNS or streaming.
- **Raw Sockets**: For low-level, custom traffic that needs direct packet handling.

## Usage

### Server Setup (for handling TCP, UDP, or raw socket traffic):
```bash
python3 python/server.py --bind-address <server_IPv6> --target-port <target_port>
```
### Client Setup (for transmitting traffic via NBTP):
```bash
python3 python/client.py --bind-address <client_IPv6> --remote-address <server_IPv6> --listen-port <listen_port>
```
### Example SSH Tunneling (TCP):

1. **Run the server**:
 ```bash
  python3 python/server.py --bind-address <server_IPv6> --target-port 22
```
2. **Run the client**:
 ```bash
python3 python/client.py --bind-address <client_IPv6> --remote-address <server_IPv6> --listen-port 22
```
3. **Connect via SSH**:
 ```bash
ssh -p 22 <client_IPv6>
```
### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Future Work

- **Go Implementation**: A Go implementation is planned for future versions to improve performance and concurrency handling.
- **Advanced Congestion Control**: While basic congestion control has been implemented, more advanced features can be added, such as RTT estimation for smarter packet pacing.
