package com.pumpgunstudios.amazonmusicrpc.mobile

object DiagnosticsFormat {
    fun artworkText(track: TrackInfo): String {
        return when {
            track.hasDiscordArtwork -> "Discord-ready: ${track.artworkSource ?: "URL"}"
            track.hasArtwork -> "Local only: ${track.artworkSource}"
            else -> "Not exposed"
        }
    }

    fun timeBarText(track: TrackInfo): String {
        if (!track.hasTimeBar) {
            return when {
                track.positionMs == null && track.durationMs == null -> "Missing position and duration"
                track.positionMs == null -> "Missing position"
                else -> "Missing duration"
            }
        }
        val positionSource = track.positionSource ?: "unknown position"
        val durationSource = track.durationSource ?: "unknown duration"
        return "Ready: ${formatMs(track.positionMs)} / ${formatMs(track.durationMs)} ($positionSource, $durationSource)"
    }

    fun lookupText(track: TrackInfo): String {
        val source = track.lookupSource ?: return "No lookup result"
        val lookupAlbum = track.lookupAlbum?.takeIf { it.isNotBlank() }
        val metadataAlbum = track.album?.takeIf { it.isNotBlank() }
        return when {
            lookupAlbum == null -> source
            metadataAlbum == null -> "$source album: $lookupAlbum"
            metadataAlbum.trim().equals(lookupAlbum.trim(), ignoreCase = true) -> "$source album match: $lookupAlbum"
            else -> "$source album differs: $lookupAlbum"
        }
    }

    fun formatMs(value: Long?): String {
        val totalSeconds = ((value ?: 0L) / 1000L).coerceAtLeast(0L)
        val minutes = totalSeconds / 60L
        val seconds = totalSeconds % 60L
        return "$minutes:${seconds.toString().padStart(2, '0')}"
    }

    fun sanitizeDiagnostic(value: String): String {
        return value
            .replace(Regex("mfa\\.[A-Za-z0-9_-]+"), "mfa.[redacted]")
            .replace(Regex("[A-Za-z0-9_-]{24}\\.[A-Za-z0-9_-]{6}\\.[A-Za-z0-9_-]{20,}"), "[redacted-token]")
            .take(240)
    }
}
