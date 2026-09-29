// Copyright (c) Microsoft Corporation. Licensed under the MIT License.
import com.microsoft.foundry.local.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.concurrent.locks.LockSupport;
import java.util.regex.Pattern;
import javax.sound.sampled.AudioSystem;

public final class EnglishStreamingProbe {
    public static void main(String[] args) throws Exception {
        byte[] pcm;
        try (var input = AudioSystem.getAudioInputStream(Path.of(args[4]).toFile())) {
            var format = input.getFormat();
            if (format.getSampleRate() != 16000 || format.getSampleSizeInBits() != 16
                    || format.getChannels() != 1 || format.isBigEndian()) {
                throw new IllegalArgumentException("Expected PCM16LE, 16000 Hz, mono");
            }
            pcm = input.readAllBytes();
        }
        var results = new ArrayList<String>();
        var locale = Pattern.compile("<[a-z]{2}-[A-Z]{2}>");
        try (var manager = new FoundryLocalManager(new Configuration(
                "EnglishStreamingQualification", Path.of(args[0]), Path.of(args[1]), Path.of(args[2])))) {
            var model = manager.catalog().getModel(args[3]);
            if (!model.isCached()) throw new IllegalStateException("Verified model cache is required");
            model.load();
            // Repeat the public fixture after a pause long enough to cross the model's VAD boundary.
            byte[] repeated = Arrays.copyOf(pcm, pcm.length * 2 + 128000);
            System.arraycopy(pcm, 0, repeated, pcm.length + 128000, pcm.length);
            for (byte[] audio : new byte[][] {pcm, repeated}) {
                long start = System.nanoTime();
                var tokens = new StringBuilder();
                long[] firstToken = {-1};
                try (var session = model.createAudioSession();
                     var transcription = session.streamPcm(PcmFormat.SPEECH, event -> {
                         if (event.kind() != SpeechEvent.Kind.TOKEN) {
                             throw new IllegalStateException("Unexpected streaming event: " + event.kind());
                         }
                         if (!event.text().isEmpty() && firstToken[0] < 0) firstToken[0] = System.nanoTime() - start;
                         tokens.append(event.text());
                     })) {
                    for (int offset = 0; offset < audio.length; offset += 3200) {
                        int end = Math.min(audio.length, offset + 3200);
                        transcription.writePcm(Arrays.copyOfRange(audio, offset, end));
                        long deadline = start + end * 1_000_000_000L / 32000;
                        long remaining;
                        while ((remaining = deadline - System.nanoTime()) > 0) LockSupport.parkNanos(remaining);
                    }
                    long stop = System.nanoTime();
                    transcription.finishInput();
                    var result = transcription.await(Duration.ofMinutes(2));
                    double stopMillis = (System.nanoTime() - stop) / 1_000_000.0;
                    if (result.cancelled() || result.text().isBlank() || !result.text().equals(tokens.toString())
                            || locale.matcher(result.text()).find()) {
                        throw new IllegalStateException("Raw English streaming/final contract failed");
                    }
                    results.add("{\"seconds\":" + audio.length / 32000.0
                            + ",\"streamingText\":" + quote(tokens.toString())
                            + ",\"finalText\":" + quote(result.text())
                            + ",\"firstTokenMs\":" + firstToken[0] / 1_000_000.0
                            + ",\"stopToFinalMs\":" + stopMillis + "}");
                }
            }
            Files.writeString(Path.of(args[5]), "{\"model\":" + quote(args[3])
                    + ",\"runtime\":" + quote(manager.runtimeVersion())
                    + ",\"cases\":[" + String.join(",", results) + "]}\n");
        }
    }

    private static String quote(String text) {
        var output = new StringBuilder("\"");
        for (char c : text.toCharArray()) {
            if (c == '"' || c == '\\') output.append('\\').append(c);
            else if (c < 32) output.append(String.format("\\u%04x", (int) c));
            else output.append(c);
        }
        return output.append('"').toString();
    }
}
