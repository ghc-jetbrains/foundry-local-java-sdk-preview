// Copyright (c) Microsoft Corporation. Licensed under the MIT License.
import com.microsoft.foundry.local.CancellationToken;
import com.microsoft.foundry.local.Configuration;
import com.microsoft.foundry.local.FoundryLocalManager;
import com.microsoft.foundry.local.Model;
import java.nio.file.Path;

public final class ModelPreparer {
    private ModelPreparer() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Expected runtime directory, cache directory, app-data directory, and model ID");
        }
        var configuration =
                new Configuration("java-native-integration", Path.of(args[0]), Path.of(args[1]), Path.of(args[2]));
        try (var manager = new FoundryLocalManager(configuration)) {
            Model model = manager.catalog().getModel(args[3]);
            if (!model.isCached()) {
                model.download(new CancellationToken(), value -> System.err.printf("model-download=%.1f%%%n", value));
            }
            if (!model.isCached()) {
                throw new IllegalStateException("Model download completed without a cached model");
            }
        }
    }
}
