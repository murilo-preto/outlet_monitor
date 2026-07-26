"""Parse Lenovo's free-text spec strings into comparable values.

Every product carries the same seven `classification` labels, so a label that
goes missing means the source shape changed — each parser returns None in that
case rather than guessing, and None is stored as NULL rather than 0. A filter
asking for "at least 16 GB" must exclude an unparsed row, not silently treat it
as an empty machine.

Every pattern here was written against the full set of distinct values in a
real export (2026-07-25: 123 products, 44 distinct RAM strings, 27 storage, 40
screen, 56 CPU, 14 GPU) rather than a sample, because most of the difficulty is
in the long tail: Lenovo mixes pt-BR and English, decimal commas and points,
three different inch marks, and at least one typo in their own data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bump when any pattern below changes. storage._ensure_parsed_specs re-parses
# every stored row when the version on disk is older than this, so correcting a
# regex fixes history on the next deploy instead of only new scrapes.
PARSER_VERSION = 1

RAM_LABEL = "Memória"
STORAGE_LABEL = "Armazenamento"
SCREEN_LABEL = "Tela"
CPU_LABEL = "Processador"
GPU_LABEL = "Placa de Vídeo"

PARSED_FIELDS = ("ram_gb", "storage_gb", "screen_in", "cpu_brand", "cpu_model", "gpu_discrete")

# Trademark marks, the modifier letter "a" Lenovo uses in "11ᵃ geração", and
# non-breaking spaces all appear mid-token and would otherwise break \b anchors.
_NOISE = str.maketrans({"™": "", "®": "", "©": "", "ᵃ": "a", " ": " "})

_PARENS = re.compile(r"\([^()]*\)")

# "2x 8GB", "2 x 8 GB" — a multiplier states the module layout, so the total is
# the product, not either number on its own.
_RAM_MULTIPLIER = re.compile(r"(\d+)\s*x\s*(\d+)\s*GB", re.IGNORECASE)
_RAM_TOKEN = re.compile(r"(\d+)\s*GB", re.IGNORECASE)

# The unit must sit against the number, or "M.2 2242" and "PCIe 4.0x4" parse as
# capacities. TB is folded to GB so one column can be compared and sorted.
_STORAGE_TOKEN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(GB|TB)\b", re.IGNORECASE)

# Three different inch marks occur in the data: ", '' and U+2033. The resolution
# in "(1920 x 1080)" must not be mistaken for a size, hence the required mark.
_SCREEN = re.compile(r"(\d{2}(?:[.,]\d)?)\s*(?:\"|''|″|”)")

# Ordered: the first that matches wins. Each captures the model as it should be
# displayed, normalised to single spaces.
_CPU_PATTERNS = (
    # The trailing \d* is what makes 11th-gen "i5-1135G7" parse: the suffix is
    # letters *then* digits, so a pattern ending in [A-Z]* leaves the trailing
    # \b sitting between two word characters and fails to match at all.
    re.compile(r"\b(i[3579]-\d{4,5}[A-Z]*\d*)\b"),
    re.compile(r"\b(Ryzen)\s+(\d)\s+(\d{4}[A-Z]*)\b", re.IGNORECASE),
    re.compile(r"\b(Ultra)\s+(\d)\s+(\d{3}[A-Z]*)\b", re.IGNORECASE),
    re.compile(r"\b(Celeron|Pentium|Athlon)\s+([A-Z]?\d{3,4}[A-Z]*)\b", re.IGNORECASE),
    # Intel's post-2024 naming, e.g. "Intel Core 3 100U" — no "i" prefix, so
    # "Core" is part of the model name rather than a prefix to drop.
    re.compile(r"\b(Core)\s+(\d)\s+(\d{3}[A-Z]+)\b"),
)

_AMD = re.compile(r"\bAMD\b|\bRyzen\b|\bAthlon\b", re.IGNORECASE)
# "ntel" is not a typo here: it is Lenovo's, in a live listing. Brand detection
# falls through to the Core/Celeron families and the i5- model shape so a
# mangled vendor name still resolves.
_INTEL = re.compile(r"\bn?tel\b|\bCore\b|\bCeleron\b|\bPentium\b|\bi[3579]-", re.IGNORECASE)

# Checked before the discrete patterns: "AMD Radeon 610M integrada" and
# "Integrated AMD Radeon Graphics" both name a discrete-sounding family while
# being integrated parts, and Lenovo writes it in either language. The stem
# stops at "integra" for exactly that reason — pt-BR "integrada" and English
# "integrated" diverge at the next character.
_GPU_INTEGRATED = re.compile(r"integra|\biris\b|\buhd\b|\bhd graphics\b", re.IGNORECASE)
_GPU_DISCRETE = re.compile(r"geforce|\brtx\b|\bgtx\b|radeon\s+rx|quadro|\bmx\d{3}", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedSpecs:
    ram_gb: int | None = None
    storage_gb: int | None = None
    screen_in: float | None = None
    cpu_brand: str | None = None
    cpu_model: str | None = None
    gpu_discrete: bool | None = None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(_NOISE)).strip()


def _strip_parens(value: str) -> str:
    """Remove parenthesised segments, innermost first, until none remain.

    Lenovo states a total and then breaks it down in brackets — "16 GB
    DDR5(8 GB SODIMM + 8 GB Soldado)" is 16 GB, not 32. Removing the brackets
    leaves exactly the total. They nest, so this repeats rather than doing one
    pass.
    """
    previous = None
    while previous != value:
        previous = value
        value = _PARENS.sub(" ", value)
    return value


def _parse_ram_gb(value: str) -> int | None:
    text = _strip_parens(_normalize(value))

    multiplier = _RAM_MULTIPLIER.search(text)
    if multiplier:
        return int(multiplier.group(1)) * int(multiplier.group(2))

    # No brackets and no multiplier means the modules are listed additively:
    # "8GB Soldered DDR4-3200 + 8GB SODIMM DDR4-3200" is a 16 GB machine.
    tokens = [int(m.group(1)) for m in _RAM_TOKEN.finditer(text)]
    return sum(tokens) if tokens else None


def _parse_storage_gb(value: str) -> int | None:
    text = _normalize(value)
    total = 0
    for match in _STORAGE_TOKEN.finditer(text):
        size = float(match.group(1).replace(",", "."))
        total += size * 1024 if match.group(2).upper() == "TB" else size
    return int(total) if total else None


def _parse_screen_in(value: str) -> float | None:
    match = _SCREEN.search(_normalize(value))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _parse_cpu(value: str) -> tuple[str | None, str | None]:
    text = _normalize(value)

    model = None
    for pattern in _CPU_PATTERNS:
        match = pattern.search(text)
        if match:
            model = " ".join(part for part in match.groups() if part)
            break

    if _AMD.search(text):
        brand = "AMD"
    elif _INTEL.search(text):
        brand = "Intel"
    else:
        brand = None

    return brand, model


def _parse_gpu_discrete(value: str) -> bool | None:
    text = _normalize(value)
    if _GPU_INTEGRATED.search(text):
        return False
    if _GPU_DISCRETE.search(text):
        return True
    return None


def parse_specs(specs: list[dict[str, str]]) -> ParsedSpecs:
    """Pull comparable values out of a product's label/value spec list."""
    by_label = {entry.get("label", ""): entry.get("value", "") for entry in specs or []}
    cpu_brand, cpu_model = _parse_cpu(by_label.get(CPU_LABEL, ""))

    return ParsedSpecs(
        ram_gb=_parse_ram_gb(by_label.get(RAM_LABEL, "")),
        storage_gb=_parse_storage_gb(by_label.get(STORAGE_LABEL, "")),
        screen_in=_parse_screen_in(by_label.get(SCREEN_LABEL, "")),
        cpu_brand=cpu_brand,
        cpu_model=cpu_model,
        gpu_discrete=_parse_gpu_discrete(by_label.get(GPU_LABEL, "")),
    )
