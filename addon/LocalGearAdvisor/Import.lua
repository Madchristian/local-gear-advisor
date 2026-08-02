-- Strict, narrow decoder for the single-profile transport blob produced by
-- the desktop companion's import_codec.py (magic "LGA2:", a SHA-256 integrity
-- digest, then a small custom canonical grammar -- see import_codec.py's
-- module docstring for the exact grammar). Never loadstring/load/eval: this
-- file only tokenizes bytes and builds plain Lua tables; a malicious paste
-- is always inert data, never executable code.
--
-- The grammar decode here is schema-directed (each of the transport's fixed
-- field positions has one known expected token kind) rather than a fully
-- generic bencode-value engine, so the parser stays as narrow as the single
-- fixed profile shape it accepts -- an unknown/misplaced field is rejected
-- immediately rather than "parsed then discarded". The resulting flat table
-- is handed to Core.lua's NS.Schema.IsValidProfileShape() for the exact same
-- semantic bounds (ranges, key sets, hash formats, ...) LocalGearAdvisorDB/
-- LocalGearAdvisorResults entries already have to satisfy, so the two never
-- drift apart.

local ADDON_NAME = ...
LocalGearAdvisorNS = LocalGearAdvisorNS or {}
local NS = LocalGearAdvisorNS

local TRANSPORT_MAGIC = "LGA2:"
local MAX_TRANSPORT_CHARS = 256 * 1024
local MAX_PARSE_DEPTH = 8
local MAX_CONTAINER_ITEMS = 20000
local MAX_STRING_BYTES = 1000000
local MAX_LENGTH_PREFIX_DIGITS = 9
local MAX_INT_DIGITS = 20
local MAX_REAL_DIGITS = 64
local DIGEST_HEX_LEN = 64

--------------------------------------------------------------------------
-- Low-level tokenizer

local function expectChar(state, ch)
  if state.pos > state.len or state.text:sub(state.pos, state.pos) ~= ch then
    return false, "expected '" .. ch .. "' in transport payload"
  end
  state.pos = state.pos + 1
  return true, nil
end

local function scanUntil(state, terminator, maxChars, what)
  local start = state.pos
  while state.pos <= state.len and state.text:sub(state.pos, state.pos) ~= terminator do
    state.pos = state.pos + 1
    if state.pos - start > maxChars then
      return nil, what .. " token is too long"
    end
  end
  if state.pos > state.len then
    return nil, "unterminated " .. what .. " token"
  end
  local body = state.text:sub(start, state.pos - 1)
  state.pos = state.pos + 1
  return body, nil
end

local function parseIntToken(state)
  local ok, err = expectChar(state, "i")
  if not ok then return nil, err end
  local digits, serr = scanUntil(state, "e", MAX_INT_DIGITS, "integer")
  if serr then return nil, serr end
  if not (digits == "0" or digits:match("^[1-9]%d*$")) then
    return nil, "malformed integer token"
  end
  return tonumber(digits), nil
end

local function parseRealToken(state)
  local ok, err = expectChar(state, "f")
  if not ok then return nil, err end
  local digits, serr = scanUntil(state, "e", MAX_REAL_DIGITS, "real")
  if serr then return nil, serr end
  if not digits:match("^%-?%d+%.%d+$") then
    return nil, "malformed real token"
  end
  return tonumber(digits), nil
end

-- Standard UTF-8 well-formedness check (RFC 3629): rejects overlong
-- encodings, lone/misplaced continuation bytes, surrogate-half codepoints
-- (U+D800-U+DFFF) and codepoints above U+10FFFF.
local function isValidUtf8(s)
  local i, n = 1, #s
  while i <= n do
    local b1 = s:byte(i)
    if b1 < 0x80 then
      i = i + 1
    elseif b1 >= 0xC2 and b1 <= 0xDF then
      local b2 = s:byte(i + 1)
      if not b2 or b2 < 0x80 or b2 > 0xBF then return false end
      i = i + 2
    elseif b1 == 0xE0 then
      local b2, b3 = s:byte(i + 1), s:byte(i + 2)
      if not b2 or b2 < 0xA0 or b2 > 0xBF then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      i = i + 3
    elseif (b1 >= 0xE1 and b1 <= 0xEC) or (b1 >= 0xEE and b1 <= 0xEF) then
      local b2, b3 = s:byte(i + 1), s:byte(i + 2)
      if not b2 or b2 < 0x80 or b2 > 0xBF then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      i = i + 3
    elseif b1 == 0xED then
      local b2, b3 = s:byte(i + 1), s:byte(i + 2)
      if not b2 or b2 < 0x80 or b2 > 0x9F then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      i = i + 3
    elseif b1 == 0xF0 then
      local b2, b3, b4 = s:byte(i + 1), s:byte(i + 2), s:byte(i + 3)
      if not b2 or b2 < 0x90 or b2 > 0xBF then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      if not b4 or b4 < 0x80 or b4 > 0xBF then return false end
      i = i + 4
    elseif b1 >= 0xF1 and b1 <= 0xF3 then
      local b2, b3, b4 = s:byte(i + 1), s:byte(i + 2), s:byte(i + 3)
      if not b2 or b2 < 0x80 or b2 > 0xBF then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      if not b4 or b4 < 0x80 or b4 > 0xBF then return false end
      i = i + 4
    elseif b1 == 0xF4 then
      local b2, b3, b4 = s:byte(i + 1), s:byte(i + 2), s:byte(i + 3)
      if not b2 or b2 < 0x80 or b2 > 0x8F then return false end
      if not b3 or b3 < 0x80 or b3 > 0xBF then return false end
      if not b4 or b4 < 0x80 or b4 > 0xBF then return false end
      i = i + 4
    else
      return false
    end
  end
  return true
end

local function parseBytestringToken(state)
  local lengthText, lerr = scanUntil(state, ":", MAX_LENGTH_PREFIX_DIGITS, "length prefix")
  if lerr then return nil, lerr end
  if not (lengthText == "0" or lengthText:match("^[1-9]%d*$")) then
    return nil, "malformed length prefix"
  end
  local length = tonumber(lengthText)
  if length > MAX_STRING_BYTES then
    return nil, "string field exceeds the maximum length"
  end
  local hexLen = length * 2
  if state.pos + hexLen - 1 > state.len then
    return nil, "truncated string field"
  end
  local hexChars = state.text:sub(state.pos, state.pos + hexLen - 1)
  if not hexChars:match("^[0-9a-f]*$") then
    return nil, "malformed hex-encoded string field"
  end
  state.pos = state.pos + hexLen
  local bytes = {}
  for i = 1, length do
    bytes[i] = string.char(tonumber(hexChars:sub(i * 2 - 1, i * 2), 16))
  end
  local raw = table.concat(bytes)
  if not isValidUtf8(raw) then
    return nil, "string field is not valid UTF-8"
  end
  return raw, nil
end

-- A baselineGear slot / itemName value is either a bytestring or 'n' (none).
-- 'none' decodes to Lua `false`, matching the flat aggregate's existing
-- false-sentinel convention for "no value" (Lua tables cannot hold a stored
-- `nil`, and Core.lua already treats `false` as the empty-slot marker).
local function parseStringOrNoneToken(state)
  if state.pos > state.len then return nil, "transport payload ended unexpectedly" end
  local char = state.text:sub(state.pos, state.pos)
  if char == "n" then
    state.pos = state.pos + 1
    return false, nil
  end
  if char:match("%d") then
    return parseBytestringToken(state)
  end
  return nil, "expected a string or none token"
end

--------------------------------------------------------------------------
-- Schema-directed container parsing: every dict position in this transport
-- has a fixed, known set of allowed keys and a fixed per-key value parser.
-- Reused generically so key ordering/duplicate/allowlist/count enforcement
-- lives in exactly one place.

local function parseDict(state, depth, fieldParsers)
  if depth > MAX_PARSE_DEPTH then
    return nil, "transport payload exceeds the maximum nesting depth"
  end
  local ok, err = expectChar(state, "d")
  if not ok then return nil, err end
  local out = {}
  local previousKey = nil
  local count = 0
  while true do
    if state.pos > state.len then return nil, "unterminated dict" end
    if state.text:sub(state.pos, state.pos) == "e" then
      state.pos = state.pos + 1
      break
    end
    count = count + 1
    if count > MAX_CONTAINER_ITEMS then
      return nil, "dict exceeds the maximum field count"
    end
    local key, kerr = parseBytestringToken(state)
    if kerr then return nil, kerr end
    if previousKey ~= nil and key <= previousKey then
      return nil, "dict keys are not in strict canonical ascending order"
    end
    previousKey = key
    local parser = fieldParsers[key]
    if not parser then
      return nil, "unexpected transport field: " .. key
    end
    local value, verr = parser(state, depth + 1)
    if verr then return nil, verr end
    out[key] = value
  end
  for key in pairs(fieldParsers) do
    if out[key] == nil then
      return nil, "transport payload is missing required field: " .. key
    end
  end
  return out, nil
end

local function fieldString(state) return parseBytestringToken(state) end
local function fieldStringOrNone(state) return parseStringOrNoneToken(state) end
local function fieldInt(state) return parseIntToken(state) end
local function fieldReal(state) return parseRealToken(state) end

local IDENTITY_FIELD_PARSERS = {
  region = fieldString,
  realm = fieldString,
  name = fieldString,
  specId = fieldInt,
}

local TRAITSYSTEMS_FIELD_PARSERS = {
  omnium_talents = fieldString,
}

local ITEM_FIELD_PARSERS = {
  options = fieldString,
  itemId = fieldInt,
  itemName = fieldStringOrNone,
  fingerprint = fieldString,
  bestSlot = fieldString,
  candidateDps = fieldReal,
  deltaPercent = fieldReal,
  iterations = fieldInt,
}

local function parseItemsList(state, depth)
  if depth > MAX_PARSE_DEPTH then
    return nil, "transport payload exceeds the maximum nesting depth"
  end
  local ok, err = expectChar(state, "l")
  if not ok then return nil, err end
  local items = {}
  local count = 0
  while true do
    if state.pos > state.len then return nil, "unterminated list" end
    if state.text:sub(state.pos, state.pos) == "e" then
      state.pos = state.pos + 1
      break
    end
    count = count + 1
    if count > MAX_CONTAINER_ITEMS then
      return nil, "list exceeds the maximum item count"
    end
    local item, ierr = parseDict(state, depth + 1, ITEM_FIELD_PARSERS)
    if ierr then return nil, ierr end
    items[count] = item
  end
  return items, nil
end

local function buildBaselineGearFieldParsers()
  local slots = (NS.Schema and NS.Schema.BASELINE_SLOTS) or {}
  local parsers = {}
  for _, slot in ipairs(slots) do
    parsers[slot] = fieldStringOrNone
  end
  return parsers
end

local function identityField(state, depth) return parseDict(state, depth, IDENTITY_FIELD_PARSERS) end
local function traitSystemsField(state, depth)
  return parseDict(state, depth, TRAITSYSTEMS_FIELD_PARSERS)
end
local function baselineGearField(state, depth)
  return parseDict(state, depth, buildBaselineGearFieldParsers())
end

local PROFILE_FIELD_PARSERS = {
  identity = identityField,
  class = fieldString,
  spec = fieldString,
  level = fieldInt,
  race = fieldString,
  talents = fieldString,
  traitSystems = traitSystemsField,
  baselineGear = baselineGearField,
  fightStyle = fieldString,
  baselineDps = fieldReal,
  simcVersion = fieldString,
  simcRevision = fieldString,
  gameVersion = fieldString,
  dbcSource = fieldString,
  profileHash = fieldString,
  generatedAt = fieldInt,
  items = parseItemsList,
}

--------------------------------------------------------------------------
-- Transform the schema-directed parse tree into the flat profile shape
-- Core.lua's LocalGearAdvisorResults/LocalGearAdvisorDB entries already use.

local function transformProfile(raw)
  local profile = {
    region = raw.identity.region,
    server = raw.identity.realm,
    characterName = raw.identity.name,
    specID = raw.identity.specId,
    class = raw.class,
    spec = raw.spec,
    level = raw.level,
    race = raw.race,
    talents = raw.talents,
    traitSystems = raw.traitSystems,
    baselineGear = raw.baselineGear,
    fightStyle = raw.fightStyle,
    baselineDps = raw.baselineDps,
    simcVersion = raw.simcVersion,
    simcRevision = raw.simcRevision,
    gameVersion = raw.gameVersion,
    dbcSource = raw.dbcSource,
    profileHash = raw.profileHash,
    generatedAt = raw.generatedAt,
    items = {},
  }
  for _, item in ipairs(raw.items) do
    if profile.items[item.options] ~= nil then
      return nil, "transport payload has a duplicate item option key"
    end
    profile.items[item.options] = {
      itemID = item.itemId,
      name = item.itemName,
      fingerprint = item.fingerprint,
      bestSlot = item.bestSlot,
      candidateDps = item.candidateDps,
      deltaPercent = item.deltaPercent,
      iterations = item.iterations,
      status = "simulated",
    }
  end
  return profile, nil
end

--------------------------------------------------------------------------
-- Public entry point, mirroring import_codec.py's decode_profile_transport:
-- returns (profile, nil) on success or (nil, errorMessage) on any defect.
-- No caller may treat a partially-parsed result as trustworthy; every
-- rejection path here returns nil for the profile.

function NS.DecodeProfileTransport(text)
  if type(text) ~= "string" then return nil, "transport must be text" end
  local trimmed = text:match("^[ \t\r\n]*(.-)[ \t\r\n]*$")
  if trimmed == "" then return nil, "transport is empty" end
  if trimmed:find("[\128-\255]") then return nil, "transport must be pure ASCII" end
  if #trimmed > MAX_TRANSPORT_CHARS then return nil, "transport exceeds the maximum size" end
  if trimmed:sub(1, #TRANSPORT_MAGIC) ~= TRANSPORT_MAGIC then
    return nil, "transport has an unrecognized or missing version marker"
  end

  local rest = trimmed:sub(#TRANSPORT_MAGIC + 1)
  if #rest < DIGEST_HEX_LEN + 1 or rest:sub(DIGEST_HEX_LEN + 1, DIGEST_HEX_LEN + 1) ~= ":" then
    return nil, "transport is missing a valid integrity digest"
  end
  local digest = rest:sub(1, DIGEST_HEX_LEN)
  if not digest:match("^[0-9a-f]+$") then
    return nil, "transport integrity digest is malformed"
  end
  local payload = rest:sub(DIGEST_HEX_LEN + 2)
  if payload == "" then return nil, "transport payload is empty" end

  if not NS.Sha256Hex then
    return nil, "transport integrity check is unavailable"
  end
  local computed = NS.Sha256Hex(payload)
  if computed ~= digest then
    return nil, "transport integrity digest does not match the payload"
  end

  local state = { text = payload, pos = 1, len = #payload }
  local raw, perr = parseDict(state, 1, PROFILE_FIELD_PARSERS)
  if perr then return nil, perr end
  if state.pos <= state.len then
    return nil, "transport payload has trailing data"
  end

  local profile, terr = transformProfile(raw)
  if terr then return nil, terr end

  local schema = NS.Schema
  if not schema or not schema.IsValidProfileShape then
    return nil, "transport schema validator is unavailable"
  end
  if not schema.IsValidProfileShape(profile) then
    return nil, "transport payload failed schema validation"
  end
  return profile, nil
end

--------------------------------------------------------------------------
-- Transactional DB apply/undo/delete. This is the ONLY place that ever
-- assigns LocalGearAdvisorDB/LocalGearAdvisorUndo, so every write to the
-- account-wide SavedVariables DB goes through the exact same validation and
-- one-step-undo bookkeeping.
--
-- LocalGearAdvisorDB keeps the identical {schemaVersion=2, profiles={...}}
-- shape as LocalGearAdvisorResults (and is read by the exact same
-- NS.Schema.ValidProfiles), so it is never given an extra field that would
-- make Core.lua's tooltip-time validator see it as malformed. The one-step
-- undo snapshot therefore lives in a SEPARATE SavedVariable,
-- LocalGearAdvisorUndo, shaped as
--   { identityKey = <string>, previous = <profile-or-nil>, applied = <profile-or-nil> }
-- where "previous"/"applied" is the profile at that identity before/after
-- the operation (nil meaning "did not exist"). Undo verifies the CURRENT DB
-- entry still matches "applied" before reverting to "previous", so it can
-- never clobber a newer import or edit that happened after the snapshot was
-- taken; on success it clears itself (one-shot).

local function deepCopy(value)
  if type(value) ~= "table" then return value end
  local copy = {}
  for k, v in pairs(value) do
    copy[k] = deepCopy(v)
  end
  return copy
end

local function deepEqual(a, b)
  if a == b then return true end
  if type(a) ~= "table" or type(b) ~= "table" then return false end
  for k, v in pairs(a) do
    if not deepEqual(v, b[k]) then return false end
  end
  for k in pairs(b) do
    if a[k] == nil then return false end
  end
  return true
end

local function findByIdentityKey(profiles, identityKey, schema)
  for index, entry in ipairs(profiles) do
    if schema.IdentityKey(entry) == identityKey then
      return entry, index
    end
  end
  return nil, nil
end

-- Validates fully, then -- only on success -- replaces (or adds) exactly the
-- matching identity's entry and activates it immediately (no reload/logout
-- needed: Core.lua reads LocalGearAdvisorDB fresh on every tooltip). On any
-- failure LocalGearAdvisorDB is left completely untouched (same object).
function NS.ApplyProfileTransport(profile)
  local schema = NS.Schema
  if not schema or not schema.IsValidProfileShape or not schema.ValidProfiles
      or not schema.IdentityKey then
    return false, "transport schema validator is unavailable"
  end
  if not schema.IsValidProfileShape(profile) then
    return false, "profile failed schema validation"
  end
  if type(NS.CheckProfileFreshness) ~= "function" then
    return false, "profile freshness validator is unavailable"
  end
  local fresh, freshnessReason = NS.CheckProfileFreshness(profile)
  if not fresh then return false, freshnessReason end

  local existingProfiles
  if LocalGearAdvisorDB == nil then
    existingProfiles = {}
  else
    existingProfiles = schema.ValidProfiles(LocalGearAdvisorDB)
    if not existingProfiles then
      return false, "the existing local database is damaged; import refused to avoid data loss"
    end
  end

  local key = schema.IdentityKey(profile)
  local previousEntry = findByIdentityKey(existingProfiles, key, schema)
  local newProfiles = {}
  local replaced = false
  local storedProfile = deepCopy(profile)
  for index, entry in ipairs(existingProfiles) do
    if schema.IdentityKey(entry) == key then
      newProfiles[index] = storedProfile
      replaced = true
    else
      newProfiles[index] = entry
    end
  end
  if not replaced then
    newProfiles[#newProfiles + 1] = storedProfile
  end

  local pendingDB = { schemaVersion = 2, profiles = newProfiles }
  -- Deep-copied, not aliased to the live DB entry or the caller's `profile`:
  -- the snapshot must stay a frozen point-in-time record so later tampering
  -- of the live entry is actually detectable as "changed since", instead of
  -- silently mutating the snapshot along with it.
  local pendingUndo = {
    identityKey = key,
    previous = deepCopy(previousEntry),
    applied = deepCopy(profile),
  }
  -- All hookable validation/copy/identity work is complete. Check the clock
  -- once more immediately before the only two mutations, with no function
  -- calls between this check and those assignments.
  fresh, freshnessReason = NS.CheckProfileFreshness(profile)
  if not fresh then return false, freshnessReason end
  LocalGearAdvisorDB = pendingDB
  LocalGearAdvisorUndo = pendingUndo
  return true, nil
end

-- Removes exactly one identity's entry from LocalGearAdvisorDB (never from
-- the immutable LocalGearAdvisorResults fallback, which this file never
-- writes to at all) and leaves a one-step undo snapshot, same as apply.
function NS.DeleteDbProfile(identityKey)
  local schema = NS.Schema
  if not schema or not schema.ValidProfiles or not schema.IdentityKey then
    return false, "transport schema validator is unavailable"
  end
  if type(identityKey) ~= "string" or identityKey == "" then
    return false, "no profile identity given to delete"
  end
  if LocalGearAdvisorDB == nil then
    return false, "there is no imported profile to delete"
  end
  local existingProfiles = schema.ValidProfiles(LocalGearAdvisorDB)
  if not existingProfiles then
    return false, "the existing local database is damaged; delete refused"
  end

  local removedEntry = findByIdentityKey(existingProfiles, identityKey, schema)
  if not removedEntry then
    return false, "no matching imported profile to delete"
  end
  local newProfiles = {}
  for _, entry in ipairs(existingProfiles) do
    if schema.IdentityKey(entry) ~= identityKey then
      newProfiles[#newProfiles + 1] = entry
    end
  end

  LocalGearAdvisorDB = { schemaVersion = 2, profiles = newProfiles }
  LocalGearAdvisorUndo = {
    identityKey = identityKey,
    previous = deepCopy(removedEntry),
    applied = nil,
  }
  return true, nil
end

-- Reverts exactly the last apply/delete, and only if nothing else has
-- touched that identity's DB entry since (otherwise a newer, unrelated
-- import or edit would silently be lost). One-shot: clears the snapshot on
-- success so it can never be replayed.
function NS.UndoLastImport()
  local snapshot = LocalGearAdvisorUndo
  if type(snapshot) ~= "table" or type(snapshot.identityKey) ~= "string" then
    return false, "no undo available"
  end
  local schema = NS.Schema
  if not schema or not schema.ValidProfiles or not schema.IdentityKey
      or not schema.IsValidProfileShape then
    return false, "transport schema validator is unavailable"
  end
  if LocalGearAdvisorDB == nil then
    return false, "there is nothing to undo"
  end
  local currentProfiles = schema.ValidProfiles(LocalGearAdvisorDB)
  if not currentProfiles then
    return false, "the current local database is damaged; undo refused"
  end

  local function validSnapshotProfile(value)
    return value == nil
        or (schema.IsValidProfileShape(value)
            and schema.IdentityKey(value) == snapshot.identityKey)
  end
  if not validSnapshotProfile(snapshot.previous)
      or not validSnapshotProfile(snapshot.applied)
      or (snapshot.previous == nil and snapshot.applied == nil) then
    return false, "the undo snapshot is damaged; undo refused"
  end

  local currentEntry, currentIndex = findByIdentityKey(
    currentProfiles, snapshot.identityKey, schema
  )
  local matchesApplied
  if snapshot.applied == nil then
    matchesApplied = currentEntry == nil
  else
    matchesApplied = currentEntry ~= nil and deepEqual(currentEntry, snapshot.applied)
  end
  if not matchesApplied then
    return false, "the database changed since this import; undo refused to avoid overwriting it"
  end

  local newProfiles = {}
  for index, entry in ipairs(currentProfiles) do
    newProfiles[index] = entry
  end
  if currentEntry ~= nil then
    if snapshot.previous == nil then
      table.remove(newProfiles, currentIndex)
    else
      newProfiles[currentIndex] = deepCopy(snapshot.previous)
    end
  elseif snapshot.previous ~= nil then
    newProfiles[#newProfiles + 1] = deepCopy(snapshot.previous)
  end

  LocalGearAdvisorDB = { schemaVersion = 2, profiles = newProfiles }
  LocalGearAdvisorUndo = nil
  return true, nil
end
