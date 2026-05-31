package com.pumpgunstudios.amazonmusicrpc.mobile

import java.net.URLEncoder

object MetadataText {
    fun cleanTitle(value: String): String {
        return value
            .replace(Regex("\\s*\\[.*?]"), "")
            .replace(Regex("\\s*\\(feat\\..*?\\)", RegexOption.IGNORE_CASE), "")
            .replace(Regex("\\s*\\(ft\\..*?\\)", RegexOption.IGNORE_CASE), "")
            .trim()
    }

    fun cleanArtist(value: String): String {
        return value
            .substringBefore(" feat.")
            .substringBefore(" ft.")
            .trim()
    }

    fun encode(value: String): String {
        return URLEncoder.encode(value, "UTF-8")
    }

    fun matchesResult(resultTitle: String, resultArtist: String, expectedTitle: String, expectedArtist: String): Boolean {
        val titleMatches = normalize(resultTitle) == normalize(expectedTitle)
        if (!titleMatches) return false
        if (expectedArtist.isBlank()) return true
        return normalize(resultArtist) == normalize(expectedArtist)
    }

    fun albumScore(resultAlbum: String, expectedAlbum: String, index: Int): Int {
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

    fun upscaleItunesArtwork(url: String): String {
        return url
            .replace("100x100bb", "600x600bb")
            .replace("100x100-999", "600x600-999")
    }

    fun normalize(value: String): String {
        return value.lowercase().replace(Regex("[^a-z0-9]+"), "")
    }
}
