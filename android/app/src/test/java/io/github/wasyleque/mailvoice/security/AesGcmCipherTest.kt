package io.github.wasyleque.mailvoice.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

class AesGcmCipherTest {

    private lateinit var cipher: AesGcmCipher
    private lateinit var secretKey: SecretKey

    @Before
    fun setUp() {
        cipher = AesGcmCipher()
        val keyGen = KeyGenerator.getInstance("AES")
        keyGen.init(256)
        secretKey = keyGen.generateKey()
    }

    @Test
    fun testEncryptDecryptRoundTrip() {
        val original = "a1b2c3d4e5f67890secretToken_with_Polish_chars_Zażółć_gęślą_jaźń!"
        val encrypted = cipher.encrypt(original, secretKey)
        val decrypted = cipher.decrypt(encrypted, secretKey)

        assertEquals(original, decrypted)
        assertNotEquals(original, encrypted)
    }

    @Test
    fun testEachEncryptionGeneratesUniqueIv() {
        val original = "same_plain_text"
        val enc1 = cipher.encrypt(original, secretKey)
        val enc2 = cipher.encrypt(original, secretKey)

        assertNotEquals(enc1, enc2)
        assertEquals(original, cipher.decrypt(enc1, secretKey))
        assertEquals(original, cipher.decrypt(enc2, secretKey))
    }

    @Test
    fun testDecryptionFailsOnTamperedCiphertext() {
        val original = "super_secret_token"
        val encrypted = cipher.encrypt(original, secretKey)

        // Modify byte in Base64 string
        val tampered = if (encrypted.endsWith("A")) {
            encrypted.dropLast(1) + "B"
        } else {
            encrypted.dropLast(1) + "A"
        }

        assertThrows(Exception::class.java) {
            cipher.decrypt(tampered, secretKey)
        }
    }

    @Test
    fun testDecryptionFailsOnTooShortData() {
        val shortBase64 = java.util.Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3, 4))
        assertThrows(IllegalArgumentException::class.java) {
            cipher.decrypt(shortBase64, secretKey)
        }
    }
}
