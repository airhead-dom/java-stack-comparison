// Fake upstream for the /composite workload. Reactive on purpose: it must hold
// thousands of delayed connections without ever becoming the bottleneck.
plugins {
    id("benchmark-app")
}

dependencies {
    implementation(project(":common"))
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
}
