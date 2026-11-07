"""Named area boxes (west, south, east, north in degrees, WGS84) with their target map scales."""

AREAS = {
    # West coast around Bergen: the hardest generalisation case (thousands of skerries and islands),
    # deep fjords (Sognefjorden > 1,200 m) and the Norwegian Trench offshore. Proof of concept.
    "vestland": {"box": (3.5, 59.0, 7.5, 61.5), "crs": "EPSG:25832"},
}
