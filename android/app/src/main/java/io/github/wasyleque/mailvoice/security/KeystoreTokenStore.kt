package io.github.wasyleque.mailvoice.security

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

/**
 * Bezpieczny magazyn poświadczeń na urządzeniu Android.
 * Klucz symetryczny AES-256 jest generowany i przechowywany w sprzętowym AndroidKeyStore.
 * Zaszyfrowane wartości (token Bearer, odcisk palca, host, ID urządzenia) są składowane
 * w prywatnych SharedPreferences aplikacji.
 */
class KeystoreTokenStore(
    context: Context,
    private val cipher: AesGcmCipher = AesGcmCipher()
) : TokenStore {

    companion object {
        private const val PREFS_NAME = "mailvoice_secure_prefs"
        private const val KEY_ALIAS = "mailvoice_credentials_key"
        private const val KEYSTORE_PROVIDER = "AndroidKeyStore"

        private const val PREF_TOKEN = "enc_token"
        private const val PREF_FP = "enc_fp"
        private const val PREF_HOST = "enc_host"
        private const val PREF_PORT = "port"
        private const val PREF_DEVICE_ID = "enc_device_id"
    }

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    @Synchronized
    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }
        if (keyStore.containsAlias(KEY_ALIAS)) {
            val entry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
            if (entry != null) {
                return entry.secretKey
            }
        }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            KEYSTORE_PROVIDER
        )
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()

        keyGenerator.init(spec)
        return keyGenerator.generateKey()
    }

    @Synchronized
    override fun saveCredentials(
        token: String,
        serverFingerprint: String,
        serverHost: String,
        serverPort: Int,
        deviceId: String?
    ) {
        val key = getOrCreateKey()
        val encToken = cipher.encrypt(token, key)
        val encFp = cipher.encrypt(serverFingerprint, key)
        val encHost = cipher.encrypt(serverHost, key)
        val encDeviceId = deviceId?.let { cipher.encrypt(it, key) }

        val editor = prefs.edit()
            .putString(PREF_TOKEN, encToken)
            .putString(PREF_FP, encFp)
            .putString(PREF_HOST, encHost)
            .putInt(PREF_PORT, serverPort)

        if (encDeviceId != null) {
            editor.putString(PREF_DEVICE_ID, encDeviceId)
        } else {
            editor.remove(PREF_DEVICE_ID)
        }
        editor.apply()
    }

    @Synchronized
    override fun getToken(): String? {
        val enc = prefs.getString(PREF_TOKEN, null) ?: return null
        return try {
            cipher.decrypt(enc, getOrCreateKey())
        } catch (_: Exception) {
            null
        }
    }

    @Synchronized
    override fun getServerFingerprint(): String? {
        val enc = prefs.getString(PREF_FP, null) ?: return null
        return try {
            cipher.decrypt(enc, getOrCreateKey())
        } catch (_: Exception) {
            null
        }
    }

    @Synchronized
    override fun getServerHost(): String? {
        val enc = prefs.getString(PREF_HOST, null) ?: return null
        return try {
            cipher.decrypt(enc, getOrCreateKey())
        } catch (_: Exception) {
            null
        }
    }

    @Synchronized
    override fun getServerPort(): Int {
        return prefs.getInt(PREF_PORT, 0)
    }

    @Synchronized
    override fun getDeviceId(): String? {
        val enc = prefs.getString(PREF_DEVICE_ID, null) ?: return null
        return try {
            cipher.decrypt(enc, getOrCreateKey())
        } catch (_: Exception) {
            null
        }
    }

    @Synchronized
    override fun clear() {
        prefs.edit().clear().apply()
    }

    @Synchronized
    override fun isPaired(): Boolean {
        return !getToken().isNullOrBlank() && !getServerFingerprint().isNullOrBlank()
    }
}
