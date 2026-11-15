package tbvalidate;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.brigadier.StringReader;
import com.mojang.serialization.Codec;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.JsonOps;

import java.io.Reader;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

/**
 * Validates the pack with Minecraft 1.21.11's own deserializers (obfuscated client jar,
 * names resolved from Mojang's official mappings):
 *   BlockModel.fromStream, ClientItem.CODEC, AnimationMetadataSection.CODEC,
 *   PackMetadataSection.codecForPackType(CLIENT_RESOURCES), ItemParser + ItemInput (give commands).
 */
public class GameParse {
    static int errors = 0;

    static Class<?> cls(String n) throws Exception { return Class.forName(n); }

    static Object staticCodec(String clsName) throws Exception {
        for (Field f : cls(clsName).getDeclaredFields()) {
            if (Modifier.isStatic(f.getModifiers()) && Codec.class.isAssignableFrom(f.getType()) && f.getName().equals("a")) {
                f.setAccessible(true);
                return f.get(null);
            }
        }
        throw new IllegalStateException("no codec in " + clsName);
    }

    static Method method(Class<?> c, String name, Class<?>... types) throws Exception {
        Method m = c.getDeclaredMethod(name, types);
        m.setAccessible(true);
        return m;
    }

    static void ok(String what) { System.out.println("  OK   " + what); }
    static void fail(String what, Object why) { errors++; System.out.println("  FAIL " + what + " -> " + why); }

    @SuppressWarnings({"unchecked", "rawtypes"})
    public static void main(String[] args) throws Exception {
        Path pack = Path.of(args[0]);
        // SharedConstants.tryDetectVersion(); Bootstrap.bootStrap();
        method(cls("w"), "a").invoke(null);
        method(cls("amv"), "a").invoke(null);
        // client-side registries normally filled by Minecraft's client bootstrap (ClientBootstrap)
        for (String c : new String[]{"ihl", "ihx", "ijk", "iiu", "gha", "ikj"}) method(cls(c), "a").invoke(null);
        Object version = method(cls("w"), "b").invoke(null);
        Object clientRes = cls("azn").getField("a").get(null);
        Object packVer = method(cls("aa"), "a", cls("azn")).invoke(version, clientRes);
        System.out.println("Game version: " + method(cls("aa"), "c").invoke(version)
                + "  resource pack version: " + packVer);

        // ---- pack.mcmeta
        System.out.println("pack.mcmeta");
        Codec packCodec = (Codec) method(cls("baa"), "b", cls("azn")).invoke(null, clientRes);
        JsonObject meta = JsonParser.parseString(Files.readString(pack.resolve("pack.mcmeta"))).getAsJsonObject();
        DataResult r = packCodec.parse(JsonOps.INSTANCE, meta.get("pack"));
        if (r.error().isPresent()) fail("pack.mcmeta", r.error().get()); else ok("pack.mcmeta -> " + r.result().get());

        // ---- models
        System.out.println("models (BlockModel.fromStream)");
        Method fromStream = method(cls("hqe"), "a", Reader.class);
        try (Stream<Path> s = Files.list(pack.resolve("assets/timeblades/models/item"))) {
            for (Path p : (Iterable<Path>) s.sorted()::iterator) {
                try (Reader rd = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
                    Object model = fromStream.invoke(null, rd);
                    ok(p.getFileName() + " parsed (" + model.getClass().getSimpleName() + ")");
                } catch (Exception e) {
                    fail(p.getFileName().toString(), e.getCause() != null ? e.getCause() : e);
                }
            }
        }

        // ---- item model definitions
        System.out.println("items (ClientItem.CODEC)");
        Codec itemCodec = (Codec) staticCodec("ihf");
        try (Stream<Path> s = Files.list(pack.resolve("assets/timeblades/items"))) {
            for (Path p : (Iterable<Path>) s.sorted()::iterator) {
                JsonElement j = JsonParser.parseString(Files.readString(p));
                DataResult res = itemCodec.parse(JsonOps.INSTANCE, j);
                if (res.error().isPresent()) fail(p.getFileName().toString(), res.error().get());
                else ok(p.getFileName() + " -> " + res.result().get());
            }
        }

        // ---- animation metadata
        System.out.println("animations (AnimationMetadataSection.CODEC)");
        Codec animCodec = (Codec) staticCodec("imz");
        try (Stream<Path> s = Files.list(pack.resolve("assets/timeblades/textures/item/time_blade"))) {
            for (Path p : (Iterable<Path>) s.sorted()::iterator) {
                if (!p.toString().endsWith(".mcmeta")) continue;
                JsonObject j = JsonParser.parseString(Files.readString(p)).getAsJsonObject();
                DataResult res = animCodec.parse(JsonOps.INSTANCE, j.get("animation"));
                if (res.error().isPresent()) fail(p.getFileName().toString(), res.error().get());
                else ok(p.getFileName() + " -> " + res.result().get());
            }
        }

        // ---- give commands: parse the item argument exactly like /give does
        System.out.println("give commands (ItemParser + ItemInput.createItemStack)");
        Object lookup = method(cls("pc"), "a").invoke(null);
        Constructor<?> parserCtor = cls("gr").getDeclaredConstructor(cls("jf$a"));
        parserCtor.setAccessible(true);
        Object parser = parserCtor.newInstance(lookup);
        Method parse = method(cls("gr"), "a", StringReader.class);
        Class<?> resCls = cls("gr$a");
        Method resItem = method(resCls, "a");
        Method resComps = method(resCls, "b");
        Constructor<?> inputCtor = cls("gq").getDeclaredConstructor(cls("jd"), cls("kg"));
        inputCtor.setAccessible(true);
        Method create = method(cls("gq"), "a", int.class, boolean.class);
        List<String> lines = Files.readAllLines(pack.resolve("commands.txt"));
        int n = 0;
        for (String line : lines) {
            if (!line.startsWith("/give ")) continue;
            String rest = line.substring(6);
            String sel = rest.substring(0, rest.indexOf(' '));
            String itemArg = rest.substring(sel.length() + 1);
            String count = "1";
            if (!itemArg.endsWith("]")) {
                int lastSpace = itemArg.lastIndexOf(' ');
                count = itemArg.substring(lastSpace + 1);
                itemArg = itemArg.substring(0, lastSpace);
            }
            try {
                StringReader sr = new StringReader(itemArg);
                Object res = parse.invoke(parser, sr);
                if (sr.canRead()) throw new IllegalStateException("trailing input: " + sr.getRemaining());
                Object input = inputCtor.newInstance(resItem.invoke(res), resComps.invoke(res));
                Object stack = create.invoke(input, Integer.parseInt(count), false);
                ok("give #" + (++n) + " -> " + stack + " " + resComps.invoke(res));
            } catch (Exception e) {
                fail("give: " + line, e.getCause() != null ? e.getCause() : e);
            }
        }
        System.out.println(errors == 0 ? "GAME PARSE: ALL OK" : ("GAME PARSE: " + errors + " ERROR(S)"));
        System.exit(errors == 0 ? 0 : 1);
    }
}
