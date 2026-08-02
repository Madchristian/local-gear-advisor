-- Pure-arithmetic SHA-256 (FIPS 180-4) for Lua 5.1. WoW's Lua runtime does not
-- expose bit32/bitlib, so every bitwise primitive here is built from plain
-- integer arithmetic on doubles (exact for the 32-bit-range values used):
--   * XOR is looked up a byte at a time from a precomputed 256x256 table.
--   * AND/OR are derived algebraically from XOR: for integers a,b >= 0,
--     a + b == 2*AND(a,b) + XOR(a,b), so AND = (a+b-XOR)/2, OR = (a+b+XOR)/2.
--   * Rotate/shift are done via floor-division and multiplication by 2^n.
-- This is the standard public SHA-256 algorithm; nothing here is copied from
-- any third-party addon or library.

LocalGearAdvisorNS = LocalGearAdvisorNS or {}
local NS = LocalGearAdvisorNS

local MASK32 = 4294967296

local XOR_BYTE = {}
for a = 0, 255 do
  local row = {}
  for b = 0, 255 do
    local x, weight, av, bv = 0, 1, a, b
    for _ = 1, 8 do
      local abit = av % 2
      local bbit = bv % 2
      if abit ~= bbit then x = x + weight end
      av = (av - abit) / 2
      bv = (bv - bbit) / 2
      weight = weight * 2
    end
    row[b] = x
  end
  XOR_BYTE[a] = row
end

local function bxor32(x, y)
  local x1 = x % 256; x = (x - x1) / 256
  local y1 = y % 256; y = (y - y1) / 256
  local x2 = x % 256; x = (x - x2) / 256
  local y2 = y % 256; y = (y - y2) / 256
  local x3 = x % 256; x = (x - x3) / 256
  local y3 = y % 256; y = (y - y3) / 256
  local x4 = x % 256
  local y4 = y % 256
  return XOR_BYTE[x1][y1]
      + XOR_BYTE[x2][y2] * 256
      + XOR_BYTE[x3][y3] * 65536
      + XOR_BYTE[x4][y4] * 16777216
end

local function band32(x, y)
  return (x + y - bxor32(x, y)) / 2
end

local function bnot32(x)
  return 4294967295 - x
end

local function rrotate(x, n)
  local divisor = 2 ^ n
  local lo = x % divisor
  local hi = (x - lo) / divisor
  return hi + lo * 2 ^ (32 - n)
end

local function rshift(x, n)
  local divisor = 2 ^ n
  return (x - x % divisor) / divisor
end

local K = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
}

local function padMessage(message)
  local length = #message
  local bitLength = length * 8
  local paddingZeros = (56 - ((length + 1) % 64)) % 64
  local hi = math.floor(bitLength / MASK32) % MASK32
  local lo = bitLength % MASK32
  local function be4(n)
    local b1 = math.floor(n / 16777216) % 256
    local b2 = math.floor(n / 65536) % 256
    local b3 = math.floor(n / 256) % 256
    local b4 = n % 256
    return string.char(b1, b2, b3, b4)
  end
  return message .. "\128" .. string.rep("\0", paddingZeros) .. be4(hi) .. be4(lo)
end

local function digestWords(message)
  local h0, h1, h2, h3, h4, h5, h6, h7 =
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19

  local padded = padMessage(message)
  local blockCount = #padded / 64
  local W = {}
  for blockIndex = 0, blockCount - 1 do
    local base = blockIndex * 64
    for i = 1, 16 do
      local o = base + (i - 1) * 4
      local b1, b2, b3, b4 = string.byte(padded, o + 1, o + 4)
      W[i] = b1 * 16777216 + b2 * 65536 + b3 * 256 + b4
    end
    for t = 17, 64 do
      local w15, w2 = W[t - 15], W[t - 2]
      local s0 = bxor32(bxor32(rrotate(w15, 7), rrotate(w15, 18)), rshift(w15, 3))
      local s1 = bxor32(bxor32(rrotate(w2, 17), rrotate(w2, 19)), rshift(w2, 10))
      W[t] = (W[t - 16] + s0 + W[t - 7] + s1) % MASK32
    end

    local a, b, c, d, e, f, g, h = h0, h1, h2, h3, h4, h5, h6, h7
    for t = 1, 64 do
      local s1 = bxor32(bxor32(rrotate(e, 6), rrotate(e, 11)), rrotate(e, 25))
      local ch = bxor32(band32(e, f), band32(bnot32(e), g))
      local temp1 = (h + s1 + ch + K[t] + W[t]) % MASK32
      local s0 = bxor32(bxor32(rrotate(a, 2), rrotate(a, 13)), rrotate(a, 22))
      local maj = bxor32(bxor32(band32(a, b), band32(a, c)), band32(b, c))
      local temp2 = (s0 + maj) % MASK32
      h = g; g = f; f = e
      e = (d + temp1) % MASK32
      d = c; c = b; b = a
      a = (temp1 + temp2) % MASK32
    end

    h0 = (h0 + a) % MASK32
    h1 = (h1 + b) % MASK32
    h2 = (h2 + c) % MASK32
    h3 = (h3 + d) % MASK32
    h4 = (h4 + e) % MASK32
    h5 = (h5 + f) % MASK32
    h6 = (h6 + g) % MASK32
    h7 = (h7 + h) % MASK32
  end

  return h0, h1, h2, h3, h4, h5, h6, h7
end

local HEX_DIGITS = "0123456789abcdef"
local function toHex32(n)
  local out = {}
  for shift = 28, 0, -4 do
    local nibble = math.floor(n / 2 ^ shift) % 16
    out[#out + 1] = HEX_DIGITS:sub(nibble + 1, nibble + 1)
  end
  return table.concat(out)
end

-- Public API: SHA-256 of a Lua byte string, as a lowercase 64-char hex digest.
function NS.Sha256Hex(message)
  if type(message) ~= "string" then return nil end
  local h0, h1, h2, h3, h4, h5, h6, h7 = digestWords(message)
  return toHex32(h0) .. toHex32(h1) .. toHex32(h2) .. toHex32(h3)
      .. toHex32(h4) .. toHex32(h5) .. toHex32(h6) .. toHex32(h7)
end
