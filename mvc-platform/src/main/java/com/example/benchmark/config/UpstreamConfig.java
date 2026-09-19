package com.example.benchmark.config;

import java.net.http.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * The upstream client is configured explicitly rather than left to defaults.
 *
 * Default HTTP connection limits vary by request factory -- the legacy
 * SimpleClientHttpRequestFactory caps at five connections per host -- and the
 * /api workload puts ~200 requests in flight. A client that throttles below
 * that would be measured instead of the thread model. The JDK client is pinned
 * here so every blocking variant uses the same one, and its HTTP/1.1 pool is
 * unbounded by default.
 */
@Configuration
public class UpstreamConfig {

	@Bean
	public RestClient upstreamClient(@Value("${benchmark.upstream.base-url}") String baseUrl) {
		return RestClient.builder()
				.baseUrl(baseUrl)
				.requestFactory(new JdkClientHttpRequestFactory(HttpClient.newHttpClient()))
				.build();
	}
}
