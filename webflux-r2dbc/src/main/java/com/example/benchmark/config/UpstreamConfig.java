package com.example.benchmark.config;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Reactor Netty's default connection pool is sized from the processor count
 * (roughly 2x cores) and would cap this variant far below the ~200 requests the
 * /api workload puts in flight -- the reactive variant would appear to lose for
 * a reason that has nothing to do with being reactive. The pool is therefore
 * raised to a value that cannot bind, matching the unbounded HTTP/1.1 pool the
 * blocking variants get from the JDK client.
 */
@Configuration
public class UpstreamConfig {

	private static final int MAX_CONNECTIONS = 2000;

	@Bean
	public WebClient upstreamClient(@Value("${benchmark.upstream.base-url}") String baseUrl) {
		ConnectionProvider provider = ConnectionProvider.builder("upstream")
				.maxConnections(MAX_CONNECTIONS)
				.pendingAcquireMaxCount(-1)
				.build();
		HttpClient httpClient = HttpClient.create(provider)
				.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000);
		return WebClient.builder()
				.baseUrl(baseUrl)
				.clientConnector(new ReactorClientHttpConnector(httpClient))
				.build();
	}
}
