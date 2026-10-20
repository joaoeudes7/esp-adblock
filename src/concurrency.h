// Cooperative concurrency helpers for the single-core targets.
//
// Everything here is single-owner by design: only loop() calls poll(), no callbacks from
// ISRs/other tasks and no shared scratch buffers. On a cooperative scheduler that removes
// the need for a mutex — the only hazards left are buffer lifetime across yields and
// re-entrancy, which each helper handles itself.
#pragma once

#include <Arduino.h>
#include <WiFiClient.h>
#include <WiFiServer.h>

namespace cc {

// One-shot flag set from an HTTP handler and consumed by the loop (e.g. "stats need a
// flash write"). Single-owner: mark() only records intent, service() does the I/O when the
// loop is idle. `volatile` in case a future ISR/timer also marks it.
class DeferredFlag {
 public:
  void mark() { _pending = true; }
  bool pending() const { return _pending; }
  bool take() {
    if (!_pending) return false;
    _pending = false;
    return true;
  }

 private:
  volatile bool _pending = false;
};

// Length-prefixed TCP relay (DNS over TCP, RFC 1035 §4.2.2), driven one step per poll().
//
// Flow: accept -> read 2-byte length -> read query -> resolve() -> (local reply |
// connect upstream, send, read reply) -> write length-prefixed reply -> close.
//
// Only the upstream connect() is still bounded-blocking (the Arduino client has no async
// connect); connectMs caps that stall. Reads are polled with available(), so the loop is
// never parked for an upstream RTT.
class TcpRelay {
 public:
  // resolve() inspects the query and either writes the reply into msg and returns its
  // length (handled locally) or returns 0 (forward upstream). Negative drops the client.
  // *qend must receive the end offset of the question (for the caller's telemetry).
  typedef int (*ResolveFn)(void* user, const IPAddress& peer, uint8_t* msg, int len, int* qend);
  typedef void (*ReplyFn)(void* user, uint8_t* msg, int len, int qend, bool forwarded);

  void begin(WiFiServer& server, IPAddress& upstream, uint16_t port, uint8_t* buf, size_t cap,
             ResolveFn resolve, ReplyFn replied, void* user, uint16_t connectMs = 200,
             uint32_t jobTimeoutMs = 4000) {
    _srv = &server;
    _upstream = &upstream;
    _port = port;
    _buf = buf;
    _cap = cap;
    _resolve = resolve;
    _replied = replied;
    _user = user;
    _connectMs = connectMs;
    _timeoutMs = jobTimeoutMs;
  }

  bool active() const { return _state != State::Idle; }

  void poll() {
    if (_busy) return; // re-entrancy guard: poll() must never be called from a handler
    _busy = true;
    if (_state == State::Idle)
      accept();
    else
      step();
    _busy = false;
  }

 private:
  enum State : uint8_t { Idle, ReadLen, ReadQuery, Connect, ReadReplyLen, ReadReply, WriteReply };

  void accept() {
    if (!_srv) return;
    WiFiClient c = _srv->accept();
    if (!c) return;
    _cli = c;
    setTimeoutMs(_cli, _ioMs);
    _deadline = millis() + _timeoutMs;
    _got = 0;
    _replyLen = 0;
    _qend = 0;
    _forwarded = false;
    _state = State::ReadLen;
  }

  void step() {
    if ((int32_t)(millis() - _deadline) >= 0) {
      closeJob();
      return;
    }
    switch (_state) {
      case ReadLen: readLen(); break;
      case ReadQuery: readQuery(); break;
      case Connect: connectUp(); break;
      case ReadReplyLen: readReplyLen(); break;
      case ReadReply: readReply(); break;
      case WriteReply: writeReply(); break;
      case Idle: break;
    }
  }

  // WiFiClient::setTimeout() is milliseconds on ESP8266 and on ESP32 core 3.x, but
  // seconds (multiplied by 1000) on ESP32 core 2.x.
  static void setTimeoutMs(WiFiClient& c, uint32_t ms) {
#if defined(ESP8266) || !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR >= 3
    c.setTimeout(ms);
#else
    c.setTimeout(ms >= 1000 ? ms / 1000 : 1);
#endif
  }

  // Non-blocking read of at most `want` bytes. Returns >0 bytes read, 0 if nothing is
  // available right now, -1 if the peer is gone.
  int drain(WiFiClient& c, uint8_t* dst, int want) {
    int avail = c.available();
    if (avail <= 0) return c.connected() ? 0 : -1;
    if (avail > want) avail = want;
    int r = c.read(dst, avail);
    if (r <= 0) return c.connected() ? 0 : -1;
    return r;
  }

  void readLen() {
    int r = drain(_cli, _hdr + _got, 2 - _got);
    if (r < 0) return closeJob();
    if (!r) return;
    _got += r;
    if (_got < 2) return;
    int qlen = (_hdr[0] << 8) | _hdr[1];
    if (qlen < 13 || qlen > (int)_cap) return closeJob();
    _need = qlen;
    _got = 0;
    _state = State::ReadQuery;
  }

  void readQuery() {
    int r = drain(_cli, _buf + _got, _need - _got);
    if (r < 0) return closeJob();
    if (!r) return;
    _got += r;
    if (_got < _need) return;
    if (!_resolve) return closeJob();
    int qend = _need;
    int rlen = _resolve(_user, _cli.remoteIP(), _buf, _need, &qend);
    _qend = qend;
    if (rlen < 0) return closeJob();
    if (rlen > 0) {
      _replyLen = rlen;
      _state = State::WriteReply;
      return;
    }
    _state = State::Connect;
  }

  void connectUp() {
    if (!_upstream) return closeJob();
#if defined(ESP8266)
    _up.setTimeout(_connectMs); // ESP8266 timeout is already milliseconds
    if (!_up.connect(*_upstream, _port)) return closeJob();
#elif !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR >= 3
    _up.setTimeout(_connectMs);
    if (!_up.connect(*_upstream, _port)) return closeJob();
#else
    // ESP32 core 2.x: setTimeout() takes seconds; the 3-arg connect takes milliseconds.
    if (!_up.connect(*_upstream, _port, _connectMs)) return closeJob();
#endif
    _up.setNoDelay(true); // after connect: before it there is no socket to set it on
    setTimeoutMs(_up, _ioMs);
    _hdr[0] = (uint8_t)(_need >> 8);
    _hdr[1] = (uint8_t)(_need & 0xFF);
    if (_up.write(_hdr, 2) != 2 || _up.write(_buf, (size_t)_need) != (size_t)_need)
      return closeJob();
    _forwarded = true;
    _got = 0;
    _state = State::ReadReplyLen;
  }

  void readReplyLen() {
    int r = drain(_up, _hdr + _got, 2 - _got);
    if (r < 0) return closeJob();
    if (!r) return;
    _got += r;
    if (_got < 2) return;
    int n = (_hdr[0] << 8) | _hdr[1];
    if (n < 12 || n > (int)_cap) return closeJob();
    _need = n;
    _got = 0;
    _state = State::ReadReply;
  }

  void readReply() {
    int r = drain(_up, _buf + _got, _need - _got);
    if (r < 0) return closeJob();
    if (!r) return;
    _got += r;
    if (_got < _need) return;
    _replyLen = _need;
    _state = State::WriteReply;
  }

  void writeReply() {
    if (_replyLen < 12 || _replyLen > (int)_cap) return closeJob();
    _hdr[0] = (uint8_t)(_replyLen >> 8);
    _hdr[1] = (uint8_t)(_replyLen & 0xFF);
    if (_cli.write(_hdr, 2) != 2 || _cli.write(_buf, (size_t)_replyLen) != (size_t)_replyLen)
      return closeJob();
    if (_replied) _replied(_user, _buf, _replyLen, _qend, _forwarded);
    closeJob();
  }

  void closeJob() {
    _up.stop();
    _cli.stop();
    _state = State::Idle;
    _got = _need = _replyLen = 0;
    _forwarded = false;
  }

  WiFiServer* _srv = nullptr;
  IPAddress* _upstream = nullptr;
  uint16_t _port = 53;
  uint8_t* _buf = nullptr;
  size_t _cap = 0;
  ResolveFn _resolve = nullptr;
  ReplyFn _replied = nullptr;
  void* _user = nullptr;
  uint16_t _connectMs = 200;
  uint16_t _ioMs = 100;
  uint32_t _timeoutMs = 4000;

  WiFiClient _cli;
  WiFiClient _up;
  State _state = State::Idle;
  bool _busy = false;
  uint8_t _hdr[2] = {0, 0};
  int _need = 0, _got = 0, _replyLen = 0, _qend = 0;
  bool _forwarded = false;
  uint32_t _deadline = 0;
};

}  // namespace cc
