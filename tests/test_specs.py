"""Every input below is a real value from a live Lenovo export, not invented."""

import pytest

from outlet_monitor.specs import ParsedSpecs, parse_specs


def specs(**by_label) -> list[dict[str, str]]:
    labels = {
        "ram": "Memória",
        "storage": "Armazenamento",
        "screen": "Tela",
        "cpu": "Processador",
        "gpu": "Placa de Vídeo",
    }
    return [{"label": labels[k], "value": v} for k, v in by_label.items()]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("8GB Soldered DDR4-3200", 8),
        ("16GB", 16),
        # Two modules listed additively — the total is the sum, and this shape
        # covers 13 of the 123 products in the 2026-07-25 export.
        ("8GB Soldered DDR4-3200 + 8GB SODIMM DDR4-3200", 16),
        ("8GB Soldered DDR4-3200 + 4GB SO-DIMM DDR4-3200", 12),
        # Total stated first, then broken down in brackets — summing here would
        # double it, which is why the brackets are stripped before counting.
        ("16 GB DDR5-4.800MT/s(8 GB SODIMM + 8 GB Soldado)", 16),
        ("24 GB DDR5-4.800MT/s(16 GB SODIMM + 8 GB Soldado)", 24),
        ("12 GB DDR4-3.200MT/s(4 GB SODIMM + 8 GB Soldado)", 12),
        ("16GB DDR4 3200 (8GB Soldado + 8GB SODIMM)", 16),
        ("16GB (8GB DDR5 5600 UDIMM + 8GB DDR5 5600 UDIMM)", 16),
        # Nested brackets.
        ("32 GB (2x 16 GB DDR5-5.600MT/s (SODIMM))", 32),
        ("32 GB (2x16 GB DDR5-5.200MT/s (SODIMM))", 32),
        ("16 GB DDR5-4.800MT/s (SODIMM)(2 x 8 GB)", 16),
        # Multipliers state the layout, so the total is the product.
        ("2x 8GB SODIMM DDR5-4800", 16),
        ("2x 8GB SO-DIMM DDR4-3200", 16),
        ("1x 16GB SODIMM DDR5-5200", 16),
        ("2x 16GB SODIMM DDR5-4800", 32),
        ("8 GB LPDDR5-5.500MHz (Soldado)", 8),
        ("4GB Soldered DDR4-2933", 4),
    ],
)
def test_ram_is_parsed_from_every_shape_lenovo_uses(value, expected):
    assert parse_specs(specs(ram=value)).ram_gb == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("256GB SSD M.2 2242 PCIe® 4.0x4 NVMe®", 256),
        ("512 GB SSD M.2 2242 PCIe Gen4 QLC", 512),
        ("1TB SSD M.2 2242 PCIe® 4.0x4 NVMe® Opal 2.0", 1024),
        ("128GB eMMC 5.1", 128),
        ("512GB", 512),
        # The trailing bay has no capacity of its own to add.
        ("256GB SSD M.2 2242 PCIe® 4.0x4 NVMe® + Empty HDD Bay", 256),
        # "M.2 2242", "2280", "4.0x4" and "Gen4" must not read as capacities.
        ("512 GB SSD M.2 2280 PCIe TLC Opal", 512),
        ("256 GB SSD M.2 2280 PCIe 4.0 NVMe x4", 256),
    ],
)
def test_storage_is_parsed_and_tb_folds_to_gb(value, expected):
    assert parse_specs(specs(storage=value)).storage_gb == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ('15.6" FHD (1920 x 1080), TN, antirreflexo', 15.6),
        # pt-BR decimal comma.
        ('15,3" WUXGA (1920 x 1200), WVA, antirreflexo', 15.3),
        ('15,6" HD (1366 x 768), TN, Antirreflexo', 15.6),
        ("15.6'' FHD", 15.6),  # two apostrophes instead of a quote
        ("Up to 14″ WUXGA+ (2240 x 1400), IPS, 300nits", 14.0),  # U+2033
        ('16" WUXGA (1920x1200) IPS 300nits Anti-glare, 45% NTSC', 16.0),
        ('14" HD (1366 x 768), TN', 14.0),
    ],
)
def test_screen_size_is_parsed_despite_three_different_inch_marks(value, expected):
    assert parse_specs(specs(screen=value)).screen_in == expected


def test_screen_ignores_the_resolution_in_brackets():
    # "1920 x 1080" is the thing most likely to be mistaken for a size.
    assert parse_specs(specs(screen='14" FHD (1920 x 1080)')).screen_in == 14.0


@pytest.mark.parametrize(
    "value,brand,model",
    [
        ("Intel Core™ i5-13420H, 8C (4P + 4E) / 12T", "Intel", "i5-13420H"),
        (
            "Processador Intel® Core™ i5-13420H de 13ª geração (núcleos de eficiência)",
            "Intel",
            "i5-13420H",
        ),
        # 11th-gen suffixes are letters *then* digits.
        ("11ª geração Intel Core i5-1135G7", "Intel", "i5-1135G7"),
        ("11ᵃ geração Intel® Core™ i5-1135G7", "Intel", "i5-1135G7"),
        ("11ª geração Intel Core i5-1145G7 vPro", "Intel", "i5-1145G7"),
        ("Intel Core™ i7-1165G7 (4C / 8T, 2.8 / 4.7GHz, 12MB)", "Intel", "i7-1165G7"),
        ("Processador Intel® Core™ i7-12650HX de 12ª geração", "Intel", "i7-12650HX"),
        ("Intel® Core™ Ultra 5 125H", "Intel", "Ultra 5 125H"),
        ("Processador Intel® Core™ Ultra 7 155U (núcleos)", "Intel", "Ultra 7 155U"),
        # Intel's post-2024 naming, with no "i" prefix at all.
        ("Intel Core™ 3 100U, 6C (2P + 4E) / 8T", "Intel", "Core 3 100U"),
        ("Intel® Celeron® N4500 (2C / 2T, 1.1 / 2.8GHz)", "Intel", "Celeron N4500"),
        ("Processador AMD Ryzen™ 3 7320U (2,40 GHz até 4,10 GHz)", "AMD", "Ryzen 3 7320U"),
        ("AMD Ryzen™ 7 7735HS (8C / 16T, 3.2 / 4.75GHz)", "AMD", "Ryzen 7 7735HS"),
        ("AMD Ryzen 3 7320U", "AMD", "Ryzen 3 7320U"),
        (" AMD Ryzen™ 5 7520U ", "AMD", "Ryzen 5 7520U"),  # stray whitespace
        ("Intel® Core™ i7-12700H ", "Intel", "i7-12700H"),
    ],
)
def test_cpu_brand_and_model_are_parsed(value, brand, model):
    parsed = parse_specs(specs(cpu=value))
    assert (parsed.cpu_brand, parsed.cpu_model) == (brand, model)


def test_cpu_survives_lenovos_own_typo():
    # Verbatim from a live listing: the vendor name lost its leading letter.
    # The model shape has to carry the brand when the brand name is mangled.
    parsed = parse_specs(specs(cpu="ntel Core™ i5-13420H,"))
    assert (parsed.cpu_brand, parsed.cpu_model) == ("Intel", "i5-13420H")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("NVIDIA® GeForce RTX™ 3060 Laptop GPU", True),
        ("GPU para laptop NVIDIA® GeForce RTX™ 4050 6GB GDDR6", True),
        ("NVIDIA® GeForce GTX 1650 4GB GDDR6", True),
        ("NVIDIA® GeForce RTX™ 2050", True),
        ("Integrada", False),
        # Names a discrete-sounding family but is an integrated part...
        ("AMD Radeon™ 610M integrada", False),
        # ...and Lenovo says so in English on some listings.
        ("Integrated AMD Radeon™ Graphics", False),
        ("Placa gráfica Intel® Arc™ integrada", False),
        ("Placa gráfica Intel® UHD integrada", False),
        # Names no vendor keyword at all and never says "integrated".
        ("Intel® Iris® Xe", False),
    ],
)
def test_gpu_discreteness(value, expected):
    assert parse_specs(specs(gpu=value)).gpu_discrete is expected


def test_unrecognised_gpu_is_unknown_rather_than_integrated():
    assert parse_specs(specs(gpu="Some Future GPU 9000")).gpu_discrete is None


@pytest.mark.parametrize("value", ["", "   ", "N/A", "Sob consulta"])
def test_unparseable_values_yield_none_not_zero(value):
    parsed = parse_specs(specs(ram=value, storage=value, screen=value, cpu=value, gpu=value))

    assert parsed.ram_gb is None
    assert parsed.storage_gb is None
    assert parsed.screen_in is None
    assert parsed.cpu_model is None
    assert parsed.gpu_discrete is None


def test_missing_labels_yield_an_empty_result():
    # A label vanishing means Lenovo changed their payload shape. That must
    # surface as absent data, not as a machine with 0 GB of everything.
    assert parse_specs([]) == ParsedSpecs()
    assert parse_specs([{"label": "Garantia", "value": "1 Ano"}]) == ParsedSpecs()
