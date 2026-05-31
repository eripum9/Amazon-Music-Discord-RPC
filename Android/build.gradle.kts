plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
}

tasks.register("hostCheck") {
    group = "verification"
    description = "Builds Android debug APKs and runs local JVM tests without an emulator."
    dependsOn(":app:testDebugUnitTest", ":fakeamazon:testDebugUnitTest", ":app:assembleDebug", ":fakeamazon:assembleDebug")
}
