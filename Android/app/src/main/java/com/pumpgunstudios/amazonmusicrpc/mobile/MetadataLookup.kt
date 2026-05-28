package com.pumpgunstudios.amazonmusicrpc.mobile

import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.URLEncoder
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
        val cleanTitle = cleanTitle(title)
        val cleanArtist = cleanArtist(artist)
        val query = encode("artist:\"$cleanArtist\" track:\"$cleanTitle\"")
        val url = "https://api.deezer.com/search?q=$query&limit=5"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val data = JSONObject(body).optJSONArray("data") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (index in 0 until data.length()) {
                val item = data.optJSONObject(index) ?: continue
                val itemArtist = item.optJSONObject("artist")?.optString("name").orEmpty()
                if (!matchesResult(item.optString("title"), itemArtist, cleanTitle, cleanArtist)) continue
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
                    val score = albumScore(result.album, albumHint, index)
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
        val query = encode("${cleanTitle(title)} ${cleanArtist(artist)}")
        val url = "https://itunes.apple.com/search?term=$query&media=music&entity=song&limit=25"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val results = JSONObject(body).optJSONArray("results") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (index in 0 until results.length()) {
                val item = results.optJSONObject(index) ?: continue
                if (!matchesResult(item.optString("trackName"), item.optString("artistName"), cleanTitle(title), cleanArtist(artist))) continue
                val art = upscaleItunesArtwork(item.optString("artworkUrl100"))
                if (art.isNotBlank()) {
                    val result = LookupResult(
                        artworkUrl = art,
                        album = item.optString("collectionName"),
                        durationMs = item.optLong("trackTimeMillis", 0L).takeIf { it > 0L },
                        source = "iTunes",
                    )
                    val score = albumScore(result.album, albumHint, index)
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
        val cleanTitle = cleanTitle(title)
        val cleanArtist = cleanArtist(artist)
        if (cleanArtist.isBlank()) return LookupResult.Empty
        val query = encode("recording:\"$cleanTitle\" AND artist:\"$cleanArtist\"")
        val url = "https://musicbrainz.org/ws/2/recording?query=$query&fmt=json&limit=10&inc=releases"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val recordings = JSONObject(body).optJSONArray("recordings") ?: return LookupResult.Empty
            var best = LookupResult.Empty
            var bestScore = -1
            for (recordingIndex in 0 until recordings.length()) {
                val recording = recordings.optJSONObject(recordingIndex) ?: continue
                if (!matchesResult(recording.optString("title"), cleanArtist, cleanTitle, cleanArtist)) continue
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
                    val score = albumScore(album, albumHint, releaseIndex + recordingIndex)
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
            .header("User-Agent", "AmazonMusicRPC-Android-Beta")
            .build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return null
            return response.body?.string()
        }
    }

    private fun cleanTitle(value: String): String {
        return value
            .replace(Regex("\\s*\\[.*?]"), "")
            .replace(Regex("\\s*\\(feat\\..*?\\)", RegexOption.IGNORE_CASE), "")
            .replace(Regex("\\s*\\(ft\\..*?\\)", RegexOption.IGNORE_CASE), "")
            .trim()
    }

    private fun cleanArtist(value: String): String {
        return value
            .substringBefore(" feat.")
            .substringBefore(" ft.")
            .trim()
    }

    private fun encode(value: String): String {
        return URLEncoder.encode(value, "UTF-8")
    }

    private fun matchesResult(resultTitle: String, resultArtist: String, expectedTitle: String, expectedArtist: String): Boolean {
        val titleMatches = normalize(resultTitle) == normalize(expectedTitle)
        if (!titleMatches) return false
        if (expectedArtist.isBlank()) return true
        return normalize(resultArtist) == normalize(expectedArtist)
    }

    private fun albumScore(resultAlbum: String, expectedAlbum: String, index: Int): Int {
        val result = normalize(resultAlbum)
        val expected = normalize(expectedAlbum)
        val rankPenalty = index.coerceAtLeast(0)
        return when {
            result.isBlank() -> 0 - rankPenalty
            expected.isBlank() -> 20 - rankPenalty
            result == expected -> 100 - rankPenalty
            result.contains(expected) || expected.contains(result) -> 70 - rankPenalty
            else -> 10 - rankPenalty
        }
    }

    private fun upscaleItunesArtwork(url: String): String {
        return url
            .replace("100x100bb", "600x600bb")
            .replace("100x100-999", "600x600-999")
    }

    private fun normalize(value: String): String {
        return value.lowercase().replace(Regex("[^a-z0-9]+"), "")
    }

    companion object {
        private const val CACHE_TTL_MS = 6 * 60 * 60 * 1000L
    }
}
