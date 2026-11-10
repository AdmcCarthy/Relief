"""The gallery card texture: averaged down for the cards, same encoding, same extent."""

import numpy as np
import render_region as rr


def test_a_narrow_grid_needs_no_card():
    assert rr.card_texture(np.zeros((900, 1800), "float32"), 250.0) is None


def test_the_card_is_the_smallest_whole_block_average_within_the_width():
    z = np.zeros((300, 4300), "float32")
    small, cell = rr.card_texture(z, 250.0, max_w=1800)
    assert cell == 750.0 and small.shape == (100, 1434)  # k = 3: 4300 / 3 rounds up to 1434 columns
    assert small.shape[1] <= 1800


def test_block_means_are_exact_and_the_last_row_and_column_are_repeated_not_cut():
    z = np.arange(5 * 7, dtype="float32").reshape(5, 7)
    small, cell = rr.card_texture(z, 100.0, max_w=4)  # k = 2
    assert cell == 200.0 and small.shape == (3, 4)
    assert small[0, 0] == z[:2, :2].mean() and small[1, 1] == z[2:4, 2:4].mean()
    assert small[2, 0] == z[4, :2].mean()  # last row repeated, so the extent is kept
    assert small[0, 3] == z[:2, 6].mean()  # last column repeated


def test_nodata_is_averaged_as_zero_like_the_full_texture():
    z = np.full((4, 8), np.nan, "float32")
    z[:, :2] = 10.0
    small, _ = rr.card_texture(z, 100.0, max_w=4)
    assert small[0, 0] == 10.0 and small[0, 1] == 0.0


def test_the_card_survives_the_16_bit_encoding_to_within_one_step():
    rng = np.random.default_rng(1)
    z = (rng.normal(0, 400, (64, 200))).astype("float32")
    small, _ = rr.card_texture(z, 100.0, max_w=100)
    back = rr.decode(rr.encode(small))
    assert np.abs(back - small).max() <= rr.STEP
