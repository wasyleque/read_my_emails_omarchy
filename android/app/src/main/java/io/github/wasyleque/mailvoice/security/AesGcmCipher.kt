package io.github.wasyleque.mailvoice.security

import java.nio.ByteBuffer
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Pomocnik kryptograficzny realizujący szyfrowanie i deszyfrowanie AES-256-GCM.
 * Każde wywołanie metody encrypt generuje unikalny 12-bajtowy wektor IV,
 * który jest doklejany na początku szyfrogramu: [12B IV][Szyfrogram + 16B GCM tag].
 */
class AesGcmCipher {

    companion object {
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val TAG_LENGTH_BIT = 128
        private const val IV_LENGTH_BYTE = 12
    }

    /**
     * Szyfruje tekst jawny za pomocą zadanego klucza symetrycznego.
     * Zwraca zakodowany ciąg Base64 zawierający IV oraz szyfrogram z tagiem uwierzytelniającym.
     */
    fun encrypt(plainText: String, secretKey: SecretKey): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey)
        val iv = cipher.iv ?: throw IllegalStateException("Cipher nie wygenerował wymaganego wektora IV.")
        val cipherBytes = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))

        val buffer = ByteBuffer.allocate(iv.size + cipherBytes.size)
        buffer.put(iv)
        buffer.put(cipherBytes)
        return Base64.getEncoder().encodeToString(buffer.array())
    }

    /**
     * Odszyfrowuje ciąg Base64 zaszyfrowany metodą [encrypt].
     * Weryfikuje integralność danych za pomocą wbudowanego tagu uwierzytelniającego GCM.
     */
    fun decrypt(encryptedBase64: String, secretKey: SecretKey): String {
        val combined = try {
            Base64.getDecoder().decode(encryptedBase64)
        } catch (e: IllegalArgumentException) {
            throw IllegalArgumentException("Błędny format danych Base64.", e)
        }

        if (combined.size < IV_LENGTH_BYTE) {
            throw IllegalArgumentException("Zaszyfrowany ciąg danych jest zbyt krótki (brak pełnego IV).")
        }

        val iv = combined.copyOfRange(0, IV_LENGTH_BYTE)
        val cipherBytes = combined.copyOfRange(IV_LENGTH_BYTE, combined.size)

        val cipher = Cipher.getInstance(TRANSFORMATION)
        val spec = GCMParameterSpec(TAG_LENGTH_BIT, iv)
        cipher.init(Cipher.DECRYPT_MODE, secretKey, spec)
        val plainBytes = cipher.doFinal(cipherBytes)
        return String(plainBytes, Charsets.UTF_8)
    }
}
