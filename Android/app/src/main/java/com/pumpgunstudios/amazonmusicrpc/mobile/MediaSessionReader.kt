package com.pumpgunstudios.amazonmusicrpc.mobile

import android.app.Service
import android.content.ComponentName
import android.content.Context
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import kotlin.math.max
import kotlin.math.min

class MediaSessionReader(private val context: Context) {
    private val manager = context.getSystemService(Service.MEDIA_SESSION_SERVICE) as MediaSessionManager
    private val listenerComponent = ComponentName(context, RpcNotificationListener::class.java)

    fun read(packageFilters: String): TrackInfo? {
        val filters = packageFilters.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val sessions = manager.getActiveSessions(listenerComponent)
        val controller = sessions.firstOrNull { controller ->
            filters.isEmpty() || filters.any { filter -> controller.packageName.equals(filter, true) }
        } ?: sessions.firstOrNull { controller ->
            controller.metadata?.getString(MediaMetadata.METADATA_KEY_TITLE)?.isNotBlank() == true
        } ?: return null
        return controller.toTrackInfo()
    }

    private fun MediaController.toTrackInfo(): TrackInfo? {
        val metadata = metadata ?: return null
        val title = metadata.getString(MediaMetadata.METADATA_KEY_TITLE)?.trim().takeUnless { it.isNullOrBlank() } ?: return null
        val artist = metadata.getString(MediaMetadata.METADATA_KEY_ARTIST)?.trim()
            ?: metadata.getString(MediaMetadata.METADATA_KEY_AUTHOR)?.trim()
            ?: metadata.getString(MediaMetadata.METADATA_KEY_ALBUM_ARTIST)?.trim()
        val album = metadata.getString(MediaMetadata.METADATA_KEY_ALBUM)?.trim()
        val artworkUri = metadata.getString(MediaMetadata.METADATA_KEY_ALBUM_ART_URI)?.trim()?.takeUnless { it.isBlank() }
            ?: metadata.getString(MediaMetadata.METADATA_KEY_ART_URI)?.trim()?.takeUnless { it.isBlank() }
            ?: metadata.getString(MediaMetadata.METADATA_KEY_DISPLAY_ICON_URI)?.trim()?.takeUnless { it.isBlank() }
        val hasSessionBitmap = metadata.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART) != null
            || metadata.getBitmap(MediaMetadata.METADATA_KEY_ART) != null
            || metadata.getBitmap(MediaMetadata.METADATA_KEY_DISPLAY_ICON) != null
        val notificationArtwork = RpcNotificationListener.artworkFor(packageName)
        val artworkSource = when {
            artworkUri != null -> "media session URI"
            hasSessionBitmap -> "media session bitmap"
            notificationArtwork?.hasArtwork == true -> notificationArtwork.source ?: "notification artwork"
            else -> null
        }
        val state = playbackState
        val metadataDuration = metadata.getLong(MediaMetadata.METADATA_KEY_DURATION).takeIf { it > 0 }
        val notificationDuration = notificationArtwork?.durationMs?.takeIf { it > 0 }
        val duration = metadataDuration ?: notificationDuration
        val now = System.currentTimeMillis()
        val statePosition = state?.accuratePositionMs(duration, now)
        val notificationPosition = notificationArtwork?.positionMs?.takeIf { it >= 0 }
        val position = statePosition ?: notificationPosition
        return TrackInfo(
            title = title,
            artist = artist,
            album = album,
            packageName = packageName,
            playbackState = state?.state,
            durationMs = duration,
            positionMs = position,
            durationSource = when {
                metadataDuration != null -> "media session"
                notificationDuration != null -> "notification"
                else -> null
            },
            positionSource = when {
                statePosition != null -> "media session"
                notificationPosition != null -> "notification"
                else -> null
            },
            artworkUri = artworkUri,
            artworkSource = artworkSource,
            lookupSource = null,
            updatedAtMs = now,
        )
    }

    private fun PlaybackState.accuratePositionMs(durationMs: Long?, nowMs: Long): Long? {
        val base = position.takeIf { it >= 0 } ?: return null
        val adjusted = if (state == PlaybackState.STATE_PLAYING && lastPositionUpdateTime > 0) {
            base + ((nowMs - lastPositionUpdateTime) * playbackSpeed).toLong()
        } else {
            base
        }
        val safe = max(0L, adjusted)
        return if (durationMs != null) min(durationMs, safe) else safe
    }
}
