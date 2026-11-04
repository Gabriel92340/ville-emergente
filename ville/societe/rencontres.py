import math

METRES_PAR_DEGRE_LATITUDE = 111_132.0
METRES_PAR_DEGRE_LONGITUDE_EQUATEUR = 111_320.0
VOISINAGE = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def en_metres(latitude: float, longitude: float, latitude_reference: float) -> tuple[float, float]:
    facteur = math.cos(math.radians(latitude_reference))
    return (
        longitude * METRES_PAR_DEGRE_LONGITUDE_EQUATEUR * facteur,
        latitude * METRES_PAR_DEGRE_LATITUDE,
    )


def paires_proches(
    positions: dict[int, tuple[float, float]], rayon_m: float
) -> list[tuple[int, int]]:
    grille: dict[tuple[int, int], list[int]] = {}
    for identifiant in sorted(positions):
        x, y = positions[identifiant]
        grille.setdefault((math.floor(x / rayon_m), math.floor(y / rayon_m)), []).append(identifiant)
    paires = []
    rayon_carre = rayon_m * rayon_m
    for identifiant in sorted(positions):
        x, y = positions[identifiant]
        colonne, ligne = math.floor(x / rayon_m), math.floor(y / rayon_m)
        for dx, dy in VOISINAGE:
            for autre in grille.get((colonne + dx, ligne + dy), ()):
                if autre <= identifiant:
                    continue
                autre_x, autre_y = positions[autre]
                if (x - autre_x) ** 2 + (y - autre_y) ** 2 <= rayon_carre:
                    paires.append((identifiant, autre))
    return sorted(paires)


class DetecteurRencontres:
    def __init__(self, rayon_m: float):
        self._rayon_m = rayon_m
        self._contacts: set[tuple[int, int]] = set()

    def actualiser(self, positions: dict[int, tuple[float, float]]) -> list[tuple[int, int]]:
        paires = paires_proches(positions, self._rayon_m)
        nouvelles = [paire for paire in paires if paire not in self._contacts]
        self._contacts = set(paires)
        return nouvelles
