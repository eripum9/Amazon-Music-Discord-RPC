package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class TrackInfoTest {
    @Test
    fun lookupFillsMissingAlbumArtworkAndDuration() {
        val track = trackInfo(album = "", artworkUri = null, durationMs = null, durationSource = null)
        val enriched = track.withLookup(
            LookupResult(
                artworkUrl = "https://example.com/wolf.jpg",
                album = "Wolf",
                durationMs = 309000L,
                source = "Deezer",
            )
        )
        assertEquals("Wolf", enriched.album)
        assertEquals("https://example.com/wolf.jpg", enriched.artworkUri)
        assertEquals("Deezer", enriched.artworkSource)
        assertEquals(309000L, enriched.durationMs)
        assertEquals("Deezer", enriched.durationSource)
    }

    @Test
    fun lookupDoesNotReplaceExistingHttpArtwork() {
        val track = trackInfo(artworkUri = "https://amazon.example/art.jpg", artworkSource = "media session URI")
        val enriched = track.withLookup(LookupResult(artworkUrl = "https://lookup.example/art.jpg", album = "Wolf", source = "Deezer"))
        assertEquals("https://amazon.example/art.jpg", enriched.artworkUri)
        assertEquals("media session URI", enriched.artworkSource)
    }

    @Test
    fun detectsDiscordArtworkAndTimeBar() {
        val ready = trackInfo(artworkUri = "https://example.com/art.jpg", durationMs = 1000L, positionMs = 0L)
        val localOnly = trackInfo(artworkUri = "content://local/art", durationMs = null, positionMs = null)
        assertTrue(ready.hasDiscordArtwork)
        assertTrue(ready.hasTimeBar)
        assertFalse(localOnly.hasDiscordArtwork)
        assertFalse(localOnly.hasTimeBar)
    }
}

fun trackInfo(
    title: String = "Rusty",
    artist: String? = "Tyler, The Creator",
    album: String? = "Wolf",
    packageName: String = "com.pumpgunstudios.amazonmusicrpc.fakeamazon",
    playbackState: Int? = PlaybackTimeline.STATE_PLAYING,
    durationMs: Long? = 309000L,
    positionMs: Long? = 1000L,
    durationSource: String? = "media session",
    positionSource: String? = "media session",
    artworkUri: String? = "https://example.com/art.jpg",
    artworkSource: String? = "media session URI",
    lookupSource: String? = null,
    lookupAlbum: String? = null,
    updatedAtMs: Long = 10000L,
): TrackInfo {
    return TrackInfo(
        title = title,
        artist = artist,
        album = album,
        packageName = packageName,
        playbackState = playbackState,
        durationMs = durationMs,
        positionMs = positionMs,
        durationSource = durationSource,
        positionSource = positionSource,
        artworkUri = artworkUri,
        artworkSource = artworkSource,
        lookupSource = lookupSource,
        lookupAlbum = lookupAlbum,
        updatedAtMs = updatedAtMs,
    )
}
