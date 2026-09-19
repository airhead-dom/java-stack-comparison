import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    java
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

dependencies {
    // Every variant is instrumented identically, or the numbers are not comparable.
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// Held constant across variants: heap, GC, and JFR. Any drift here invalidates a run.
val benchmarkJvmArgs = listOf(
    "-Xms1g",
    "-Xmx1g",
    "-XX:+UseG1GC",
    "-XX:+AlwaysPreTouch",
    "-XX:StartFlightRecording=settings=profile,dumponexit=true," +
        "filename=build/${project.name}.jfr",
)

tasks.withType<BootRun>().configureEach {
    jvmArgs = benchmarkJvmArgs
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
