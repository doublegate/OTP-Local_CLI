# 21. Specification: Specialized OTP Protocols and Algorithmic Diversity

## 1. Overview

This specification details non-standard, proprietary, and counter-based one-time password generation protocols supported by OTP-Local CLI: Steam Guard, Blizzard Mobile Authenticator, Yandex OTP, and RFC 4226 HOTP.

## 2. Specialized Algorithmic Specifications

### 2.1 Steam Guard

- Hash Function: HMAC-SHA1.
- Period: 30 seconds.
- Translation Alphabet: 26 uppercase alphanumeric characters:
  `23456789BCDFGHJKMNPQRTVWXY`
- Token Length: 5 characters.
- Extraction: The lowest 4 bytes of HMAC are converted to an integer and successively modulo-divided by 26.

### 2.2 Blizzard Mobile Authenticator

- Hash Function: HMAC-SHA1.
- Digits: 8.
- Custom Parameters: Restoration key derivation from device seed and server-side clock offset calibration.

### 2.3 Yandex OTP

- Hash Function: HMAC-SHA256.
- Digits: 8.
- PIN-prefix concatenation to seed prior to hash calculation.

## 3. RFC 4226 HOTP Counter State Engine

### 3.1 Counter Persistence

- Counter storage: Stored in an atomic, write-ahead file `~/.config/authy-local/hotp_counters.json`.
- State mutations: Counter increments immediately before token rendering to prevent replay reuse.

### 3.2 Lookahead Resynchronization Window

- RFC 4226 Section 7.4 lookahead window parameter $s = 10$.
- If a server reports authentication failure, the client can test up to $s$ future counter values to resynchronize without exposing excessive brute-force surface.

## 4. Verification and Parity

All algorithms must match standard test vectors from RFC 4226, valve-python, and python-bna test suites.
