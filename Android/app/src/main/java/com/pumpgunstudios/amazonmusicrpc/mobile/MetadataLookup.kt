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
    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .callTimeout(6, TimeUnit.SECONDS)
        .build()
    private val cache = ConcurrentHashMap<String, LookupResult>()

    fun enrich(track: TrackInfo): TrackInfo {
        val key = "${track.title}|${track.artist.orEmpty()}".lowercase()
        val lookup = cache.getOrPut(key) {
            searchDeezer(track.title, track.artist.orEmpty()).takeUnless { it.isEmpty }
                ?: searchItunes(track.title, track.artist.orEmpty()).takeUnless { it.isEmpty }
                ?: LookupResult.Empty
        }
        return track.withLookup(lookup)
    }

    private fun searchDeezer(title: String, artist: String): LookupResult {
        val cleanTitle = cleanTitle(title)
        val cleanArtist = cleanArtist(artist)
        val query = encode("artist:\"$cleanArtist\" track:\"$cleanTitle\"")
        val url = "https://api.deezer.com/search?q=$query&limit=5"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val data = JSONObject(body).optJSONArray("data") ?: return LookupResult.Empty
            for (index in 0 until data.length()) {
                val item = data.optJSONObject(index) ?: continue
                val album = item.optJSONObject("album")
                val art = album?.optString("cover_xl").orEmpty()
                    .ifBlank { album?.optString("cover_big").orEmpty() }
                    .ifBlank { album?.optString("cover_medium").orEmpty() }
                if (art.isNotBlank()) {
                    return LookupResult(
                        artworkUrl = art,
                        album = album?.optString("title").orEmpty(),
                        durationMs = item.optLong("duration", 0L).takeIf { it > 0L }?.times(1000L),
                        source = "Deezer",
                    )
                }
            }
            LookupResult.Empty
        } catch (_: Exception) {
            LookupResult.Empty
        }
    }

    private fun searchItunes(title: String, artist: String): LookupResult {
        val query = encode("${cleanTitle(title)} ${cleanArtist(artist)}")
        val url = "https://itunes.apple.com/search?term=$query&media=music&limit=5"
        return try {
            val body = get(url) ?: return LookupResult.Empty
            val results = JSONObject(body).optJSONArray("results") ?: return LookupResult.Empty
            for (index in 0 until results.length()) {
                val item = results.optJSONObject(index) ?: continue
                val art = item.optString("artworkUrl100")
                    .replace("100x100bb", "600x600bb")
                    .replace("100x100-999", "600x600-999")
                if (art.isNotBlank()) {
                    return LookupResult(
                        artworkUrl = art,
                        album = item.optString("collectionName"),
                        durationMs = item.optLong("trackTimeMillis", 0L).takeIf { it > 0L },
                        source = "iTunes",
                    )
                }
            }
            LookupResult.Empty
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
}
