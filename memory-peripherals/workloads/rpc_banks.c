#include <stdint.h>

// A small bare-metal Chipyard workload.  Each 8 MiB step selects the next
// bank with the ETH/FASED RPC mapping (bank in byte-address bits [24:23]).
// The controller/model test must still prove that this mapping reaches it.
int main(void) {
  for (uint64_t bank = 0; bank < 4; ++bank) {
    volatile uint64_t *p = (volatile uint64_t *)(uintptr_t)
        (0x80010000ull + bank * 0x800000ull);
    for (uint64_t i = 0; i < 64; ++i)
      p[i] = 0x51ce000000000000ull ^ (bank << 24) ^ (i * 0x0101010101010101ull);
  }
  for (uint64_t bank = 0; bank < 4; ++bank) {
    volatile uint64_t *p = (volatile uint64_t *)(uintptr_t)
        (0x80010000ull + bank * 0x800000ull);
    for (uint64_t i = 0; i < 64; ++i) {
      uint64_t expected = 0x51ce000000000000ull ^
          (bank << 24) ^ (i * 0x0101010101010101ull);
      if (p[i] != expected) return 1 + (int)bank;
    }
  }
  return 0;
}
