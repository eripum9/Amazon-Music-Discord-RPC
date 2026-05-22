package com.pumpgunstudios.amazonmusicrpc.fakeamazon

data class FakeTrack(
    val title: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
)

val fakeTracks = listOf(
    FakeTrack("WOLF", "Tyler, The Creator", "Wolf", 110000L),
    FakeTrack("Rusty", "Tyler, The Creator", "Wolf", 309000L),
    FakeTrack("Noid", "Tyler, The Creator", "Chromakopia+", 284000L),
)
