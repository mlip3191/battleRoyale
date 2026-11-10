"""Average carnivore bite force for a body mass, fitted in code to Wroe et al. 2005 (D-47).

The 31-row table below is from Wroe, McHenry and Thomason 2005, "Bite club", Proc. R. Soc. B
272:619, Table 1. It is publisher-copyrighted and used with PM approval (D-47, PR 148).
"""

import math

SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1564077/"

# Table 1, the 31 living species: (body mass in kg, canine bite force in N, bite force quotient).
WROE_2005_LIVING: tuple[tuple[float, float, float], ...] = (
    (8.2, 178, 97),  # Alopex lagopus
    (16.5, 314, 112),  # Canis alpinus
    (7.7, 165, 94),  # Canis aureus
    (17.5, 313, 108),  # Canis lupus dingo
    (12.3, 235, 100),  # Canis lupus hallstromi
    (18.9, 428, 142),  # Lycaon pictus
    (8.1, 164, 92),  # Vulpes vulpes
    (5.3, 114, 80),  # Urocyon cineroargentus
    (19.8, 275, 88),  # Canis latrans
    (34.7, 593, 136),  # Canis lupus lupus
    (105.2, 541, 64),  # Ursus americanus
    (128.8, 751, 78),  # Ursus arctos
    (77.2, 312, 44),  # Ursus thibetanus
    (11.4, 244, 109),  # Meles meles
    (6.2, 73, 48),  # Gennetta tigrinus
    (69.1, 773, 117),  # Crocuta crocuta
    (40.8, 545, 113),  # Hyaena hyaena
    (9.3, 151, 77),  # Proteles cristatus
    (83.2, 1014, 137),  # Panthera onca
    (186.9, 1525, 127),  # Panthera tigris
    (29.5, 472, 119),  # Acinonyx jubatus
    (7.1, 127, 75),  # Felis yagouaroundi
    (2.9, 98, 100),  # Lynx rufus
    (34.5, 472, 108),  # Felis concolor
    (2.8, 56, 58),  # Felis sylvestris
    (34.4, 595, 137),  # Neofelis nebulosa
    (294.6, 1768, 112),  # Panthera leo
    (43.1, 467, 94),  # Panthera pardus
    (3.0, 153, 179),  # Dasyurus maculatus
    (0.87, 65, 137),  # Dasyurus viverrinus
    (12.0, 418, 181),  # Sarcophilus harrisii
)


# Fit force = a x mass^b to each species' force scaled to an average quotient of 100.
def _fit() -> tuple[float, float]:
    xs = [math.log(mass) for mass, _, _ in WROE_2005_LIVING]
    ys = [math.log(force * 100 / quotient) for _, force, quotient in WROE_2005_LIVING]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mean_x) ** 2 for x in xs
    )
    return math.exp(mean_y - slope * mean_x), slope


SCALE, EXPONENT = _fit()


# The canine bite force in newtons of an average carnivore of this body mass.
def average_carnivore_bite_n(mass_kg: float) -> float:
    if mass_kg <= 0:
        raise ValueError("mass must be positive")
    return SCALE * mass_kg**EXPONENT
