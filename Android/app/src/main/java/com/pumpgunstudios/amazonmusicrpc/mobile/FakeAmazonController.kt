package com.pumpgunstudios.amazonmusicrpc.mobile

import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

object FakeAmazonController {
    const val PACKAGE_NAME = "com.pumpgunstudios.amazonmusicrpc.fakeamazon"
    private const val SERVICE_NAME = "$PACKAGE_NAME.FakeAmazonMusicService"
    private const val ACTION_PLAY = "$PACKAGE_NAME.PLAY"
    private const val ACTION_PAUSE = "$PACKAGE_NAME.PAUSE"
    private const val ACTION_STOP = "$PACKAGE_NAME.STOP"
    private const val ACTION_SEEK_FORWARD = "$PACKAGE_NAME.SEEK_FORWARD"
    private const val ACTION_SEEK_BACK = "$PACKAGE_NAME.SEEK_BACK"
    private const val ACTION_TOGGLE_ARTWORK = "$PACKAGE_NAME.TOGGLE_ARTWORK"
    private const val ACTION_TOGGLE_DURATION = "$PACKAGE_NAME.TOGGLE_DURATION"
    private const val ACTION_PLAY_TRACK = "$PACKAGE_NAME.PLAY_TRACK"
    private const val EXTRA_TRACK_INDEX = "$PACKAGE_NAME.TRACK_INDEX"

    fun isInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(PACKAGE_NAME, 0)
            true
        } catch (_: PackageManager.NameNotFoundException) {
            false
        }
    }

    fun open(context: Context): String {
        val intent = context.packageManager.getLaunchIntentForPackage(PACKAGE_NAME)
            ?: return "Fake Amazon Music is not installed"
        return try {
            context.startActivity(intent)
            "Opened Fake Amazon Music"
        } catch (_: ActivityNotFoundException) {
            "Fake Amazon Music could not be opened"
        }
    }

    fun playTrack(context: Context, trackIndex: Int): String {
        return startService(context, ACTION_PLAY_TRACK, trackIndex)
    }

    fun play(context: Context): String {
        return startService(context, ACTION_PLAY)
    }

    fun pause(context: Context): String {
        return startService(context, ACTION_PAUSE)
    }

    fun seekForward(context: Context): String {
        return startService(context, ACTION_SEEK_FORWARD)
    }

    fun seekBack(context: Context): String {
        return startService(context, ACTION_SEEK_BACK)
    }

    fun toggleArtwork(context: Context): String {
        return startService(context, ACTION_TOGGLE_ARTWORK)
    }

    fun toggleDuration(context: Context): String {
        return startService(context, ACTION_TOGGLE_DURATION)
    }

    fun stop(context: Context): String {
        return startService(context, ACTION_STOP)
    }

    private fun startService(context: Context, action: String, trackIndex: Int? = null): String {
        if (!isInstalled(context)) return "Fake Amazon Music is not installed"
        val intent = Intent(action)
            .setComponent(ComponentName(PACKAGE_NAME, SERVICE_NAME))
            .apply {
                if (trackIndex != null) putExtra(EXTRA_TRACK_INDEX, trackIndex)
            }
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && action != ACTION_STOP) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            when (action) {
                ACTION_PLAY_TRACK -> "Sent fake track ${trackIndex?.plus(1) ?: 1}"
                ACTION_PLAY -> "Sent fake playback play"
                ACTION_PAUSE -> "Sent fake playback pause"
                ACTION_SEEK_FORWARD -> "Sent fake playback seek +30s"
                ACTION_SEEK_BACK -> "Sent fake playback seek -30s"
                ACTION_TOGGLE_ARTWORK -> "Toggled fake artwork"
                ACTION_TOGGLE_DURATION -> "Toggled fake duration"
                ACTION_STOP -> "Sent fake playback stop"
                else -> "Sent fake playback action"
            }
        } catch (_: SecurityException) {
            "Fake Amazon control permission denied; reinstall both debug APKs"
        } catch (e: Exception) {
            "Fake Amazon control failed: ${e.message ?: "unknown"}"
        }
    }
}
