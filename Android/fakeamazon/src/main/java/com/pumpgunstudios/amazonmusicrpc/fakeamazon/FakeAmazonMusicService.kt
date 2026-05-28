package com.pumpgunstudios.amazonmusicrpc.fakeamazon

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlin.math.min

class FakeAmazonMusicService : Service() {
    private lateinit var mediaSession: MediaSession
    private var index = 0
    private var positionMs = 0L
    private var playing = false
    private var updatedAtMs = 0L

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        mediaSession = MediaSession(this, "Fake Amazon Music").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onPlay() = play()
                override fun onPause() = pause()
                override fun onSkipToNext() = next()
                override fun onSkipToPrevious() = previous()
                override fun onStop() = stopFake()
            })
            isActive = true
        }
        updatedAtMs = System.currentTimeMillis()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_PLAY -> play()
            ACTION_PAUSE -> pause()
            ACTION_NEXT -> next()
            ACTION_PREVIOUS -> previous()
            ACTION_PLAY_TRACK -> playTrack(intent.getIntExtra(EXTRA_TRACK_INDEX, index))
            ACTION_STOP -> stopFake()
            else -> stopSelf(startId)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        mediaSession.release()
        super.onDestroy()
    }

    private fun play() {
        syncPosition()
        playing = true
        updatedAtMs = System.currentTimeMillis()
        publish()
    }

    private fun pause() {
        syncPosition()
        playing = false
        updatedAtMs = System.currentTimeMillis()
        publish()
    }

    private fun next() {
        index = (index + 1) % fakeTracks.size
        positionMs = 0L
        updatedAtMs = System.currentTimeMillis()
        playing = true
        publish()
    }

    private fun previous() {
        index = if (index == 0) fakeTracks.lastIndex else index - 1
        positionMs = 0L
        updatedAtMs = System.currentTimeMillis()
        playing = true
        publish()
    }

    private fun playTrack(trackIndex: Int) {
        index = trackIndex.coerceIn(fakeTracks.indices)
        positionMs = 0L
        updatedAtMs = System.currentTimeMillis()
        playing = true
        publish()
    }

    private fun stopFake() {
        syncPosition()
        playing = false
        mediaSession.setPlaybackState(
            PlaybackState.Builder()
                .setState(PlaybackState.STATE_STOPPED, positionMs, 0f, System.currentTimeMillis())
                .setActions(actions())
                .build()
        )
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun syncPosition() {
        if (playing) {
            val elapsed = System.currentTimeMillis() - updatedAtMs
            positionMs = min(fakeTracks[index].durationMs, positionMs + elapsed)
        }
    }

    private fun publish() {
        syncPosition()
        val track = fakeTracks[index]
        val artwork = artworkBitmap(track)
        mediaSession.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, track.title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, track.artist)
                .putString(MediaMetadata.METADATA_KEY_ALBUM, track.album)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, track.durationMs)
                .putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, artwork)
                .putBitmap(MediaMetadata.METADATA_KEY_ART, artwork)
                .build()
        )
        mediaSession.setPlaybackState(
            PlaybackState.Builder()
                .setState(if (playing) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED, positionMs, if (playing) 1f else 0f, System.currentTimeMillis())
                .setActions(actions())
                .build()
        )
        startForeground(NOTIFICATION_ID, notification(track, artwork))
    }

    private fun actions(): Long {
        return PlaybackState.ACTION_PLAY or
            PlaybackState.ACTION_PAUSE or
            PlaybackState.ACTION_PLAY_PAUSE or
            PlaybackState.ACTION_SKIP_TO_NEXT or
            PlaybackState.ACTION_SKIP_TO_PREVIOUS or
            PlaybackState.ACTION_STOP
    }

    private fun notification(track: FakeTrack, artwork: Bitmap): Notification {
        val playPauseAction = if (playing) {
            NotificationCompat.Action(R.drawable.ic_fake_amazon, "Pause", pending(ACTION_PAUSE))
        } else {
            NotificationCompat.Action(R.drawable.ic_fake_amazon, "Play", pending(ACTION_PLAY))
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_fake_amazon)
            .setContentTitle(track.title)
            .setContentText("${track.artist} • ${track.album}")
            .setLargeIcon(artwork)
            .setProgress(track.durationMs.toInt(), positionMs.toInt(), false)
            .setOngoing(playing)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .addAction(NotificationCompat.Action(R.drawable.ic_fake_amazon, "Previous", pending(ACTION_PREVIOUS)))
            .addAction(playPauseAction)
            .addAction(NotificationCompat.Action(R.drawable.ic_fake_amazon, "Next", pending(ACTION_NEXT)))
            .build()
    }

    private fun artworkBitmap(track: FakeTrack): Bitmap {
        val bitmap = Bitmap.createBitmap(512, 512, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val background = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = when (index % 4) {
                0 -> Color.rgb(40, 214, 210)
                1 -> Color.rgb(88, 101, 242)
                2 -> Color.rgb(255, 209, 102)
                else -> Color.rgb(67, 181, 129)
            }
        }
        canvas.drawRect(0f, 0f, 512f, 512f, background)
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(16, 20, 24)
            textAlign = Paint.Align.CENTER
            textSize = 72f
            isFakeBoldText = true
        }
        canvas.drawText(track.album.take(12), 256f, 245f, text)
        text.textSize = 42f
        canvas.drawText("RPC TEST", 256f, 315f, text)
        return bitmap
    }

    private fun pending(action: String): PendingIntent {
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getService(this, action.hashCode(), Intent(this, FakeAmazonMusicService::class.java).setAction(action), flags)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, getString(R.string.fake_channel_name), NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    companion object {
        private const val CHANNEL_ID = "fake_amazon_music"
        private const val NOTIFICATION_ID = 9301
        const val ACTION_PLAY = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.PLAY"
        const val ACTION_PAUSE = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.PAUSE"
        const val ACTION_NEXT = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.NEXT"
        const val ACTION_PREVIOUS = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.PREVIOUS"
        const val ACTION_PLAY_TRACK = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.PLAY_TRACK"
        const val ACTION_STOP = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.STOP"
        const val EXTRA_TRACK_INDEX = "com.pumpgunstudios.amazonmusicrpc.fakeamazon.TRACK_INDEX"
    }
}
