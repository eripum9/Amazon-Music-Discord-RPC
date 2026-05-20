package com.pumpgunstudios.amazonmusicrpc.mobile

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = SettingsStore(this)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                RpcApp(
                    store = store,
                    startService = { RpcForegroundService.start(this) },
                    stopService = { RpcForegroundService.stop(this) },
                    openNotificationAccess = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                )
            }
        }
    }
}

@Composable
private fun RpcApp(
    store: SettingsStore,
    startService: () -> Unit,
    stopService: () -> Unit,
    openNotificationAccess: () -> Unit,
) {
    var settings by remember { mutableStateOf(store.load()) }
    var status by remember { mutableStateOf(store.status()) }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        startService()
    }

    LaunchedEffect(Unit) {
        while (true) {
            status = store.status()
            delay(1000)
        }
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Amazon Music RPC", style = MaterialTheme.typography.headlineMedium)
            Text("Android beta", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)

            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Discord Gateway mode", style = MaterialTheme.typography.titleMedium)
                    Text("Android does not expose Discord IPC, so this beta sends presence through the Discord Gateway. Leave the token empty to test metadata locally without sending anything to Discord.")
                }
            }

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.token,
                onValueChange = { settings = settings.copy(token = it) },
                label = { Text("Discord token, optional for metadata test") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.applicationId,
                onValueChange = { settings = settings.copy(applicationId = it) },
                label = { Text("Discord application ID") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.packageFilters,
                onValueChange = { settings = settings.copy(packageFilters = it) },
                label = { Text("Media package filters") },
                singleLine = true,
            )

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text("Show paused tracks", style = MaterialTheme.typography.titleMedium)
                    Text("Paused tracks stay visible without a running timer.", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = settings.showPaused, onCheckedChange = { settings = settings.copy(showPaused = it) })
            }

            Card {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Status", style = MaterialTheme.typography.titleMedium)
                    Text(status)
                }
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = {
                store.save(settings)
                status = "Saved"
            }) {
                Text("Save settings")
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = {
                store.save(settings)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    startService()
                }
            }) {
                Text("Start RPC")
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = stopService) {
                Text("Stop RPC")
            }

            Button(modifier = Modifier.fillMaxWidth(), onClick = openNotificationAccess) {
                Text("Open notification access")
            }

            Spacer(Modifier.height(12.dp))
        }
    }
}
