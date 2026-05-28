package com.pumpgunstudios.amazonmusicrpc.mobile

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
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
                    clearActivity = { RpcForegroundService.clearActivity(this) },
                    openNotificationAccess = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    openAppNotificationSettings = { openAppNotificationSettings() },
                    openBatterySettings = {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    },
                )
            }
        }
    }

    private fun openAppNotificationSettings() {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$packageName"))
        }
        startActivity(intent)
    }
}

private data class RuntimeState(
    val status: String,
    val serviceRunning: Boolean,
    val notificationListenerEnabled: Boolean,
    val postNotificationsGranted: Boolean,
    val batteryOptimized: Boolean,
    val fakeAmazonInstalled: Boolean,
    val trackDiagnostics: TrackDiagnostics,
    val diagnostics: List<String>,
)

@Composable
private fun RpcApp(
    store: SettingsStore,
    startService: () -> Unit,
    stopService: () -> Unit,
    clearActivity: () -> Unit,
    openNotificationAccess: () -> Unit,
    openAppNotificationSettings: () -> Unit,
    openBatterySettings: () -> Unit,
) {
    val context = LocalContext.current
    var settings by remember { mutableStateOf(store.load()) }
    var runtime by remember { mutableStateOf(context.runtimeState(store)) }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        runtime = context.runtimeState(store)
        if (granted) {
            store.save(settings)
            startService()
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            runtime = context.runtimeState(store)
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
            Header(runtime)
            SetupChecklist(
                runtime = runtime,
                metadataOnly = settings.token.isBlank(),
                openNotificationAccess = openNotificationAccess,
                requestNotifications = {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        openAppNotificationSettings()
                    }
                },
                openBatterySettings = openBatterySettings,
            )
            StatusCard(runtime = runtime, settings = settings)
            ControlsCard(
                canStart = runtime.notificationListenerEnabled && runtime.postNotificationsGranted,
                canClear = runtime.serviceRunning || settings.token.isNotBlank(),
                isRunning = runtime.serviceRunning,
                onStart = {
                    store.save(settings)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !runtime.postNotificationsGranted) {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        startService()
                    }
                },
                onStop = stopService,
                onClear = {
                    store.save(settings)
                    if (runtime.serviceRunning) {
                        stopService()
                    } else {
                        clearActivity()
                    }
                },
            )
            TestMetadataCard(
                companionInstalled = runtime.fakeAmazonInstalled,
                onOpen = {
                    store.appendDiagnostic(FakeAmazonController.open(context))
                    runtime = context.runtimeState(store)
                },
                onPlayTrack = { index ->
                    store.appendDiagnostic(FakeAmazonController.playTrack(context, index))
                    runtime = context.runtimeState(store)
                },
                onPlay = {
                    store.appendDiagnostic(FakeAmazonController.play(context))
                    runtime = context.runtimeState(store)
                },
                onPause = {
                    store.appendDiagnostic(FakeAmazonController.pause(context))
                    runtime = context.runtimeState(store)
                },
                onStop = {
                    store.appendDiagnostic(FakeAmazonController.stop(context))
                    runtime = context.runtimeState(store)
                },
            )
            SettingsCard(
                settings = settings,
                onSettingsChange = { settings = it },
                onSave = {
                    store.save(settings)
                    runtime = context.runtimeState(store)
                },
            )
            DiagnosticsCard(
                lines = runtime.diagnostics,
                onClear = {
                    store.clearDiagnostics()
                    runtime = context.runtimeState(store)
                },
            )
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun Header(runtime: RuntimeState) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Amazon Music RPC", style = MaterialTheme.typography.headlineMedium)
                Text("Android beta", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            }
            StatusPill(if (runtime.serviceRunning) "Running" else "Stopped", runtime.serviceRunning)
        }
        Text("Set up permissions, test metadata locally, then connect Discord when you are ready.", style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun SetupChecklist(
    runtime: RuntimeState,
    metadataOnly: Boolean,
    openNotificationAccess: () -> Unit,
    requestNotifications: () -> Unit,
    openBatterySettings: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Setup checklist", style = MaterialTheme.typography.titleMedium)
            ChecklistRow(
                title = "Notification access",
                detail = if (runtime.notificationListenerEnabled) "Enabled for reading media sessions" else "Required for media-session metadata",
                ok = runtime.notificationListenerEnabled,
                actionText = if (runtime.notificationListenerEnabled) null else "Open",
                onAction = openNotificationAccess,
            )
            ChecklistRow(
                title = "Android notifications",
                detail = if (runtime.postNotificationsGranted) "Allowed for foreground status" else "Required for the foreground service notification",
                ok = runtime.postNotificationsGranted,
                actionText = if (runtime.postNotificationsGranted) null else "Allow",
                onAction = requestNotifications,
            )
            ChecklistRow(
                title = "Battery optimization",
                detail = if (runtime.batteryOptimized) "May stop the beta during longer tests" else "Not restricted by battery optimization",
                ok = !runtime.batteryOptimized,
                actionText = if (runtime.batteryOptimized) "Open" else null,
                onAction = openBatterySettings,
            )
            ChecklistRow(
                title = "Discord mode",
                detail = if (metadataOnly) "Metadata test mode, nothing is sent to Discord" else "Gateway mode will send Rich Presence updates",
                ok = true,
                actionText = null,
                onAction = {},
            )
        }
    }
}

@Composable
private fun ChecklistRow(
    title: String,
    detail: String,
    ok: Boolean,
    actionText: String?,
    onAction: () -> Unit,
) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        StatusDot(ok)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(detail, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (actionText != null) {
            OutlinedButton(onClick = onAction) {
                Text(actionText)
            }
        }
    }
}

@Composable
private fun StatusCard(runtime: RuntimeState, settings: AppSettings) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Current status", style = MaterialTheme.typography.titleMedium)
            Text(runtime.status, style = MaterialTheme.typography.bodyLarge)
            if (runtime.trackDiagnostics.title.isNotBlank()) {
                KeyValueRow("Track", runtime.trackDiagnostics.title)
                KeyValueRow("Artist", runtime.trackDiagnostics.artist.ifBlank { "Unknown artist" })
                KeyValueRow("Album", runtime.trackDiagnostics.album.ifBlank { "Unknown album" })
            }
            KeyValueRow("Time bar", runtime.trackDiagnostics.timeBar)
            KeyValueRow("Album art", runtime.trackDiagnostics.artwork)
            KeyValueRow("Lookup", runtime.trackDiagnostics.lookup)
            KeyValueRow("Source", if (settings.packageFilters.contains("fakeamazon")) "Amazon Music + companion test app" else "Configured media packages")
            KeyValueRow("Mode", if (settings.token.isBlank()) "Local metadata test" else "Discord Gateway")
            KeyValueRow("Paused tracks", if (settings.showPaused) "Visible" else "Hidden")
        }
    }
}

@Composable
private fun ControlsCard(
    canStart: Boolean,
    canClear: Boolean,
    isRunning: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onClear: () -> Unit,
) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Controls", style = MaterialTheme.typography.titleMedium)
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(modifier = Modifier.weight(1f), enabled = canStart && !isRunning, onClick = onStart) {
                    Text("Start")
                }
                OutlinedButton(modifier = Modifier.weight(1f), enabled = isRunning, onClick = onStop) {
                    Text("Stop")
                }
            }
            OutlinedButton(modifier = Modifier.fillMaxWidth(), enabled = canClear, onClick = onClear) {
                Text("Clear Discord activity")
            }
            if (!canStart) {
                Text("Finish the required permission steps before starting RPC.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun TestMetadataCard(
    companionInstalled: Boolean,
    onOpen: () -> Unit,
    onPlayTrack: (Int) -> Unit,
    onPlay: () -> Unit,
    onPause: () -> Unit,
    onStop: () -> Unit,
) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Test metadata", style = MaterialTheme.typography.titleMedium)
            KeyValueRow("Companion app", if (companionInstalled) "Installed" else "Not installed")
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = { onPlayTrack(0) }) {
                    Text("WOLF")
                }
                Button(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = { onPlayTrack(1) }) {
                    Text("Rusty")
                }
                Button(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = { onPlayTrack(2) }) {
                    Text("Noid")
                }
            }
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = onPlay) {
                    Text("Play")
                }
                OutlinedButton(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = onPause) {
                    Text("Pause")
                }
                OutlinedButton(modifier = Modifier.weight(1f), enabled = companionInstalled, onClick = onStop) {
                    Text("Stop")
                }
            }
            OutlinedButton(modifier = Modifier.fillMaxWidth(), enabled = companionInstalled, onClick = onOpen) {
                Text("Open companion app")
            }
        }
    }
}

@Composable
private fun SettingsCard(
    settings: AppSettings,
    onSettingsChange: (AppSettings) -> Unit,
    onSave: () -> Unit,
) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Settings", style = MaterialTheme.typography.titleMedium)
            Text("Discord tokens are sensitive. This beta stores the token only in local app preferences and redacts token-shaped values from diagnostics.", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.token,
                onValueChange = { onSettingsChange(settings.copy(token = it)) },
                label = { Text("Discord token, optional for metadata test") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
            )
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.applicationId,
                onValueChange = { onSettingsChange(settings.copy(applicationId = it)) },
                label = { Text("Discord application ID") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
            )
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = settings.packageFilters,
                onValueChange = { onSettingsChange(settings.copy(packageFilters = it)) },
                label = { Text("Media package filters") },
                singleLine = true,
            )
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Show paused tracks", style = MaterialTheme.typography.titleSmall)
                    Text("Paused tracks stay visible without a running timer.", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = settings.showPaused, onCheckedChange = { onSettingsChange(settings.copy(showPaused = it)) })
            }
            Button(modifier = Modifier.fillMaxWidth(), onClick = onSave) {
                Text("Save settings")
            }
        }
    }
}

@Composable
private fun DiagnosticsCard(
    lines: List<String>,
    onClear: () -> Unit,
) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Diagnostics", style = MaterialTheme.typography.titleMedium)
                OutlinedButton(enabled = lines.isNotEmpty(), onClick = onClear) {
                    Text("Clear")
                }
            }
            if (lines.isEmpty()) {
                Text("No diagnostics yet", style = MaterialTheme.typography.bodySmall)
            } else {
                lines.takeLast(10).forEach { line ->
                    Text(line, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
                }
            }
        }
    }
}

@Composable
private fun KeyValueRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun StatusPill(text: String, ok: Boolean) {
    val color = if (ok) Color(0xFF27D66D) else Color(0xFF777D86)
    Row(
        modifier = Modifier
            .clip(CircleShape)
            .background(color.copy(alpha = 0.18f))
            .padding(horizontal = 12.dp, vertical = 7.dp),
        horizontalArrangement = Arrangement.spacedBy(7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        StatusDot(ok)
        Text(text, style = MaterialTheme.typography.labelMedium, color = color)
    }
}

@Composable
private fun StatusDot(ok: Boolean) {
    Box(
        modifier = Modifier
            .size(9.dp)
            .clip(CircleShape)
            .background(if (ok) Color(0xFF27D66D) else Color(0xFFFF6B6B)),
    )
}

private fun Context.runtimeState(store: SettingsStore): RuntimeState {
    return RuntimeState(
        status = store.status(),
        serviceRunning = store.serviceRunning(),
        notificationListenerEnabled = notificationListenerEnabled(),
        postNotificationsGranted = postNotificationsGranted(),
        batteryOptimized = batteryOptimized(),
        fakeAmazonInstalled = FakeAmazonController.isInstalled(this),
        trackDiagnostics = store.trackDiagnostics(),
        diagnostics = store.diagnostics(),
    )
}

private fun Context.notificationListenerEnabled(): Boolean {
    val enabledListeners = Settings.Secure.getString(contentResolver, "enabled_notification_listeners").orEmpty()
    return enabledListeners.split(":")
        .mapNotNull { ComponentName.unflattenFromString(it) }
        .any { it.packageName == packageName }
}

private fun Context.postNotificationsGranted(): Boolean {
    return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}

private fun Context.batteryOptimized(): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return false
    val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
    return !powerManager.isIgnoringBatteryOptimizations(packageName)
}
