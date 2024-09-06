# Request for Comments: NBTP (NoBody Transport Protocol)

## Title: **NoBody Transport Protocol (NBTP)**
**Author:** Hashara256  
**Date:** September 2024  
**RFC Number:** TBD  
**Status:** Experimental  

---

## Abstract

This document specifies the **NoBody Transport Protocol (NBTP)**, an IPv6-based transport protocol that encodes data directly into IPv6 addresses rather than using traditional payloads. NBTP is designed to evade deep packet inspection (DPI), censorship, and firewalls by embedding the data in the IPv6 address fields, eliminating packet bodies. This makes NBTP particularly useful in circumventing network blockades and restrictions on VPNs or other encrypted communication protocols. NBTP supports **TCP**, **UDP**, and **raw socket** traffic, ensuring reliable delivery with ACK/NACK mechanisms and implementing basic congestion control.

---

## Table of Contents

1. Introduction
2. Motivation and Use Cases
3. NBTP Overview
4. Data Encoding
5. Packet Structure
6. Transmission Flow
7. Reliability and Congestion Control
8. Security Considerations
9. Future Work
10. Conclusion

---

### 1. **Introduction**

The NoBody Transport Protocol (NBTP) is an experimental transport protocol that uses the IPv6 address space to transmit data. NBTP removes the traditional payload of a packet and encodes data within the address itself, bypassing deep packet inspection (DPI) mechanisms and firewalls that typically rely on inspecting packet bodies. This technique allows NBTP to evade censorship, VPN restrictions, and other network blockades.

NBTP supports common transport layer protocols like **TCP**, **UDP**, and **raw socket** communications, making it a versatile protocol that can be used in a variety of applications, including tunneling and secure communications.

---

### 2. **Motivation and Use Cases**

#### 2.1. **Bypassing Network Censorship**
NBTP can be used in environments where internet access is restricted, and specific protocols or content are blocked by firewalls or DPI systems. By embedding data into IPv6 addresses, NBTP can bypass these blocks.

#### 2.2. **Circumventing VPN Blockades**
Countries or organizations that block VPN protocols like **WireGuard**, **OpenVPN**, or **SSH** can be circumvented using NBTP. Since the data is encoded in the address, it does not have a detectable packet body, making it more difficult for firewalls to filter.

#### 2.3. **Low-Overhead Communication**
NBTP removes the traditional packet body, reducing the size of the transmitted data and allowing for lightweight communication in specific use cases like **IoT** and **microservices** that require low-latency, small-payload transmissions.

---

### 3. **NBTP Overview**

NBTP utilizes the **IPv6 address space** to encode data and employs an ACK/NACK-based reliability mechanism. Each packet transmitted via NBTP embeds a sequence number and up to 16 bytes of data in the **IPv6 address suffix**, ensuring minimal packet overhead.

#### 3.1. **Features**
- **IPv6-Based Encoding**: Uses the vast address space of IPv6 to encode data, eliminating the need for traditional payloads.
- **Supports Multiple Protocols**: Works with TCP, UDP, and raw sockets, making it adaptable to different types of traffic.
- **Reliable Transmission**: ACK/NACK system for packet delivery and retransmission.
- **Congestion Control**: Implements a basic congestion control mechanism inspired by TCP.

---

### 4. **Data Encoding**

NBTP utilizes the **128-bit IPv6 address** to encode data. The **last 48 bits** (3 blocks of 16 bits) of the IPv6 address are used to store the **sequence number** and **data payload**.

#### 4.1. **IPv6 Address Format**
`[ IPv6 Prefix (fixed, e.g., /48) ] : [ Sequence Number (8 bits) ] : [ Data (40 bits) ]`
- **Sequence Number (8 bits)**: Uniquely identifies the order of the packet, enabling reordering and reliable delivery.
- **Data (40 bits)**: Encodes up to 5 bytes of data per packet, embedded directly within the IPv6 address.

Example encoded IPv6 address:  
`2001:db8:abcd::ff02:1234:5678`  
In this example:  
- **2001:db8:abcd::** is the fixed prefix.  
- **ff02** is the sequence number.  
- **1234:5678** is the encoded data.

---

### 5. **Packet Structure**

NBTP does not use traditional packet bodies; all data is transmitted within the IPv6 address. However, an **optional empty payload** may be sent for compatibility with certain network devices that expect payloads.

#### 5.1. **Using Payloads to Bypass Firewalls**
In some cases, adding a random or specific payload can help the packet appear more legitimate to DPI systems or firewalls. This technique can make NBTP traffic resemble typical HTTP, HTTPS, or other allowed traffic patterns. Adding random or specific data in the payload is a strategy to **evade censorship or firewall detection** by mimicking real traffic.

For example:
- **Random Payloads**: Insert random data to simulate traffic noise and blend with regular internet traffic.
- **Specific Payloads**: Add data that resembles common protocol headers (e.g., HTTP or DNS) to avoid raising suspicion by censorship tools or firewalls.

#### 5.2. **Packet Components**
1. **IPv6 Header**: Carries source and destination addresses.
2. **Embedded Data**: Encoded in the suffix of the IPv6 address.
3. **Optional Payload**: Can be used to simulate legitimate traffic or meet network expectations.

---

### 6. **Transmission Flow**

NBTP follows a connectionless model for UDP and a connection-oriented model for TCP-like communication:

#### 6.1. **TCP-Like Transmission (Reliable)**
1. **Client** encodes data into IPv6 address and sends it to the NBTP server.
2. **Server** receives the packet, decodes the data, and acknowledges with an **ACK** for successful receipt.
3. If the packet is lost or out-of-sequence, the server sends a **NACK** to the client, prompting retransmission.
4. Data is reassembled on the server side based on the sequence numbers.

#### 6.2. **UDP-Like Transmission (Unreliable)**
1. **Client** encodes data into IPv6 address and sends it.
2. No ACK/NACK is expected; transmission is best-effort with no guarantee of delivery.

---

### 7. **Reliability and Congestion Control**

#### 7.1. **ACK/NACK System**
NBTP uses an acknowledgment (ACK) and negative acknowledgment (NACK) system to ensure reliable packet delivery.
- **ACK**: Sent when a packet is received and successfully processed.
- **NACK**: Sent when a packet is lost or out-of-sequence, prompting retransmission.

#### 7.2. **Congestion Control**
NBTP employs a basic congestion control mechanism inspired by TCP:
- **Slow Start**: The client begins with a small congestion window (cwnd) and increases it exponentially with each successful ACK.
- **Congestion Avoidance**: Once the congestion window reaches a threshold, it increases more slowly to avoid overwhelming the network.
- **Packet Loss Handling**: On receiving a NACK or when a timeout occurs, the client halves the congestion window and re-enters slow start.

---

### 8. **Security Considerations**

NBTP does not natively provide encryption, leaving security to higher-level protocols such as TLS or SSH. However, because the data is encoded within the IPv6 address, NBTP can evade censorship or DPI systems that typically block or inspect specific payloads or packet types.

- **Encryption**: Users can implement encryption at the application layer (e.g., TLS/SSL).
- **Privacy**: NBTP's data encoding makes it difficult for DPI systems to detect or block traffic, enhancing privacy in restrictive environments.
- **Payload Strategy**: Adding a random or specific payload can further help avoid detection by making NBTP packets appear to be legitimate traffic.

---

### 9. **Future Work**

NBTP is in its experimental stage, and several improvements are planned for future iterations:
- **Advanced Congestion Control**: Implementing RTT-based congestion control for better performance in diverse network conditions.
- **Support for IPv4**: While NBTP is primarily designed for IPv6, future versions may explore IPv4 compatibility.
- **Optimized Packet Handling**: Investigating more efficient packet encoding and decoding techniques for large-scale deployments.
- **Security Enhancements**: Potentially adding encryption or integrating with existing secure transport layers.

---

### 10. **Conclusion**

NBTP introduces a novel approach to data transmission by embedding data within the IPv6 address itself, offering a lightweight, censorship-resistant protocol for bypassing firewalls, VPN blockades, and network censorship. Its flexibility to support multiple transport protocols, combined with basic reliability and congestion control mechanisms, makes NBTP a promising tool for secure and lightweight communications in restricted environments.
