// Copyright (c) Microsoft Corporation. Licensed under the MIT License.
import com.microsoft.foundry.local.CancellationToken;
import com.microsoft.foundry.local.Configuration;
import com.microsoft.foundry.local.FoundryLocalManager;
import com.microsoft.foundry.local.Model;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PrepareModel {
    public static void main(String[] args) throws Exception {
        Configuration config = Configuration.builder("multilingual-sdk-qualification")
                .runtimeDirectory(Path.of(args[0]))
                .modelCacheDirectory(Path.of(args[1]))
                .appDataDirectory(Path.of(args[2]))
                .build();
        try (FoundryLocalManager manager = new FoundryLocalManager(config)) {
            Model model = manager.catalog().getModelVariant(args[3]);
            if (!model.info().id().equals(args[3])) throw new IllegalStateException("Model identity mismatch");
            model.download(new CancellationToken(), progress -> {});
            if (!model.isCached()) throw new IllegalStateException("Model download is incomplete");
            Files.writeString(Path.of(args[4]), model.path().toAbsolutePath().toString());
            System.out.println("Prepared " + model.info().id() + " with runtime " + manager.runtimeVersion());
        }
    }
}
