package com.pumpgunstudios.amazonmusicrpc.fakeamazon

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                FakeAmazonApp(
                    requestNotifications = { launcher ->
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        }
                    },
                    send = { action -> sendAction(this, action) },
                )
            }
        }
    }
}

@Composable
private fun FakeAmazonApp(
    requestNotifications: (androidx.activity.result.ActivityResultLauncher<String>) -> Unit,
    send: (String) -> Unit,
) {
    val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Fake Amazon Music", style = MaterialTheme.typography.headlineMedium)
            Text("Companion test app", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)

            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Purpose", style = MaterialTheme.typography.titleMedium)
                    Text("This app publishes Android media-session metadata so Amazon Music RPC can be tested without Amazon Music.")
                }
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = {
                requestNotifications(notificationPermissionLauncher)
                send(FakeAmazonMusicService.ACTION_PLAY)
            }) {
                Text("Start fake playback")
            }

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(modifier = Modifier.weight(1f), onClick = { send(FakeAmazonMusicService.ACTION_PREVIOUS) }) {
                    Text("Previous")
                }
                Button(modifier = Modifier.weight(1f), onClick = { send(FakeAmazonMusicService.ACTION_NEXT) }) {
                    Text("Next")
                }
            }

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(modifier = Modifier.weight(1f), onClick = { send(FakeAmazonMusicService.ACTION_PLAY) }) {
                    Text("Play")
                }
                Button(modifier = Modifier.weight(1f), onClick = { send(FakeAmazonMusicService.ACTION_PAUSE) }) {
                    Text("Pause")
                }
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = { send(FakeAmazonMusicService.ACTION_STOP) }) {
                Text("Stop fake playback")
            }
        }
    }
}

private fun sendAction(context: Context, action: String) {
    val intent = Intent(context, FakeAmazonMusicService::class.java).setAction(action)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
    } else {
        context.startService(intent)
    }
}
