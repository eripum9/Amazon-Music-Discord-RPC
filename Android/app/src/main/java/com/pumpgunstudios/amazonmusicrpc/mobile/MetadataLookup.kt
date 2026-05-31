package com.pumpgunstudios.amazonmusicrpc.mobile

import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

data class LookupResult(
    val artworkUrl: String = "",
    val album: String = "",
    val durationMs: Long? = null,
    val source: String = "",
) {
    val isEmpty: Boolean
        get() = artworkUrl.isBlank() && album.isBlank() && durationMs == null

    companion object {
        val Empty = LookupResult()
    }
}

class MetadataLookup {
    private data class CacheEntry(
        val result: LookupResult,
        val cachedAtMs: Long,
    )

    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .callTimeout(6, TimeUnit.SECONDS)
        .build()
    private val cache = ConcurrentHashMap<String, CacheEntry>()

    fun enrich(track: TrackInfo): TrackInfo {
        val key = "${track.title}|${track.artist.orEmpty()}|${track.album.orEmpty()}".lowercase()
        val now = System.currentTimeMillis()
        val lookup = cache[key]
            ?.takeIf { now - it.cachedAtMs < CACHE_TTL_MS }
            ?.result
            ?: lookup(track).also { result ->
                if (!result.isEmpty) {
                    cache[key] = CacheEntry(result, now)
                }
            }
        return track.withLookup(lookup)
    }

    private fun lookup(track: TrackInfo): LookupResult {
        val title = track.title
        val artist = track.artist.orEmpty()
        val album = track.album.orEmpty()
        return searchDeezer(title, artist, album).takeUnless { it.isEmpty }
            ?: searchItunes(title, artist, album).takeUnless { it.isEmpty }
            ?: searchMusicBrainzCoverArt(title, artist, album).takeUnless { it.isEmpty }
            ?: LookupResult.Empty
    }

    private fun searchDeezer(title: String, artist: String, albumHint: String): LookupResult {
        val cleanTitle = MetadataText.cleanTitle(title)
        val cleanArtist = MetadataText.cleanArtist(artist)
        val query = MetadataText.encode("artist:\"$cleanArtist\" track:\"$cleanTitle\"")
        val url = "https://api.deezer.com/search?q=$query&limit=5"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val data = JSONObject(body).optJSONArray("data") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (index in 0 until data.length()) {
                val item = data.optJSONObject(index) ?: continue
                val itemArtist = item.optJSONObject("artist")?.optString("name").orEmpty()
                if (!MetadataText.matchesResult(item.optString("title"), itemArtist, cleanTitle, cleanArtist)) continue
                val album = item.optJSONObject("album")
                val art = album?.optString("cover_xl").orEmpty()
                    .ifBlank { album?.optString("cover_big").orEmpty() }
                    .ifBlank { album?.optString("cover_medium").orEmpty() }
                if (art.isNotBlank()) {
                    val result = LookupResult(
                        artworkUrl = art,
                        album = album?.optString("title").orEmpty(),
                        durationMs = item.optLong("duration", 0L).takeIf { it > 0L }?.times(1000L),
                        source = "Deezer",
                    )
                    val score = MetadataText.albumScore(result.album, albumHint, index)
                    if (score > bestScore) {
                        best = result
                        bestScore = score
                    }
                }
            }
            best
        } catch (_: Exception) {
            LookupResult.Empty
        }
    }

    private fun searchItunes(title: String, artist: String, albumHint: String): LookupResult {
        val query = MetadataText.encode("${MetadataText.cleanTitle(title)} ${MetadataText.cleanArtist(artist)}")
        val url = "https://itunes.apple.com/search?term=$query&media=music&entity=song&limit=25"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val results = JSONObject(body).optJSONArray("results") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (index in 0 until results.length()) {
                val item = results.optJSONObject(index) ?: continue
                if (!MetadataText.matchesResult(item.optString("trackName"), item.optString("artistName"), MetadataText.cleanTitle(title), MetadataText.cleanArtist(artist))) continue
                val art = MetadataText.upscaleItunesArtwork(item.optString("artworkUrl100"))
                if (art.isNotBlank()) {
                    val result = LookupResult(
                        artworkUrl = art,
                        album = item.optString("collectionName"),
                        durationMs = item.optLong("trackTimeMillis", 0L).takeIf { it > 0L },
                        source = "iTunes",
                    )
                    val score = MetadataText.albumScore(result.album, albumHint, index)
                    if (score > bestScore) {
                        best = result
                        bestScore = score
                    }
                }
            }
            best
        } catch (_: Exception) {
            LookupResult.Empty
        }
    }

    private fun searchMusicBrainzCoverArt(title: String, artist: String, albumHint: String): LookupResult {
        val cleanTitle = MetadataText.cleanTitle(title)
        val cleanArtist = MetadataText.cleanArtist(artist)
        if (cleanArtist.isBlank()) return LookupResult.Empty
        val query = MetadataText.encode("recording:\"$cleanTitle\" AND artist:\"$cleanArtist\"")
        val url = "https://musicbrainz.org/ws/2/recording?query=$query&fmt=json&limit=10&inc=releases"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val recordings = JSONObject(body).optJSONArray("recordings") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (recordingIndex in 0 until recordings.length()) {
                val recording = recordings.optJSONObject(recordingIndex) ?: continue
                if (!MetadataText.matchesResult(recording.optString("title"), cleanArtist, cleanTitle, cleanArtist)) continue
                val releases = recording.optJSONArray("releases") ?: continue
                for (releaseIndex in 0 until releases.length()) {
                    val release = releases.optJSONObject(releaseIndex) ?: continue
                    val releaseId = release.optString("id")
                    if (releaseId.isBlank()) continue
                    val album = release.optString("title")
                    val result = LookupResult(
                        artworkUrl = "https://coverartarchive.org/release/$releaseId/front-500",
                        album = album,
                        durationMs = null,
                        source = "MusicBrainz",
                    )
                    val score = MetadataText.albumScore(album, albumHint, releaseIndex + recordingIndex)
                    if (score > bestScore) {
                        best = result
                        bestScore = score
                    }
                }
            }
            best
        } catch (_: Exception) {
            LookupResult.Empty
        }
    }

    private fun get(url: String): String? {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "AmazonMusicRPC-Android")
            .build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return null
            return response.body?.string()
        }
    }

    companion object {
        private const val CACHE_TTL_MS = 6 * 60 * 60 * 1000L
    }
}
