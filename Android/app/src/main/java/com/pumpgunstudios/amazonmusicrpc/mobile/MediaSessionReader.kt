package com.pumpgunstudios.amazonmusicrpc.mobile

import android.app.Service
import android.content.ComponentName
import android.content.Context
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager

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
        return TrackInfo(
            title = title,
            artist = artist,
            album = album,
            packageName = packageName,
            playbackState = playbackState?.state,
            durationMs = metadata.getLong(MediaMetadata.METADATA_KEY_DURATION).takeIf { it > 0 },
            positionMs = playbackState?.position?.takeIf { it >= 0 },
            updatedAtMs = System.currentTimeMillis(),
        )
    }
}
