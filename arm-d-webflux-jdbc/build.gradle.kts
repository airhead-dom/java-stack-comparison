// The common real-world hybrid: reactive web layer, blocking JDBC offloaded to
// boundedElastic. Included because a lot of production code looks like this.
plugins {
    id("benchmark-app")
}

dependencies {
    implementation(project(":common"))
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-webclient")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
    testImplementation("org.springframework.boot:spring-boot-starter-data-jdbc-test")
}
