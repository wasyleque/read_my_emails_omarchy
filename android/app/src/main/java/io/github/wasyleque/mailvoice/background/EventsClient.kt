package io.github.wasyleque.mailvoice.background

import io.github.wasyleque.mailvoice.net.PinnedTlsClient
import kotlinx.coroutines.CompletableDeferred
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

/** Wynik jednego połączenia: czy było nawiązane i czy koniec jest ostateczny (wymaga parowania). */
data class ConnectionOutcome(val fatal: FatalReason?, val wasConnected: Boolean)

/**
 * Strumień zdarzeń /v1/events przez WebSocket z przypiętym certyfikatem serwera. Token idzie
 * nagłówkiem Authorization (nie w adresie URL, który mógłby trafić do logów).
 */
class EventsClient(
    private val host: String,
    private val port: Int,
    private val token: String,
    fingerprint: String,
    private val client: OkHttpClient = PinnedTlsClient(fingerprint).okHttpClient.newBuilder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // połączenie długotrwałe; żywotność pilnuje ping
        .pingInterval(30, TimeUnit.SECONDS)
        .build(),
) {
    /** Zawiesza do zakończenia połączenia. Anulowanie korutyny zamyka gniazdo. */
    suspend fun runOnce(onConnected: () -> Unit, onEvent: (ServerEvent) -> Unit): ConnectionOutcome {
        val done = CompletableDeferred<ConnectionOutcome>()
        var opened = false
        val request = Request.Builder()
            .url("https://${bracket(host)}:$port/v1/events")
            .header("Authorization", "Bearer $token")
            .build()
        val socket = client.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    opened = true
                    onConnected()
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    EventParser.parse(text)?.let(onEvent)
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    done.complete(ConnectionOutcome(null, opened))
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    done.complete(ConnectionOutcome(ReconnectPolicy.fatalFor(response?.code, t), opened))
                }
            },
        )
        try {
            return done.await()
        } finally {
            socket.cancel()
        }
    }

    private fun bracket(h: String) = if (':' in h && !h.startsWith("[")) "[$h]" else h
}
