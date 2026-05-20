package com.pumpgunstudios.amazonmusicrpc.fakeamazon

data class FakeTrack(
    val title: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
)

val fakeTracks = listOf(
    FakeTrack("Test Signal", "Amazon Music RPC", "Android Beta Tests", 185000L),
    FakeTrack("Pause State Check", "Local Companion", "Media Session Lab", 212000L),
    FakeTrack("One Letter Album", "Regression Tester", "A", 176000L),
    FakeTrack("Long Timer Drift", "Playback Probe", "Accuracy Suite", 247000L),
)
