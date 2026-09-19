// Deliberately NOT a Boot application and deliberately dependency-free.
// Holds only the domain records and the schema, so every arm queries identical
// data. Anything web- or persistence-related here would couple the layer under
// test and invalidate the comparison.
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
