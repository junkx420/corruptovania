using System.Security.Cryptography;
using System.Text;
using MP3Randomizer;
using Xunit;

namespace MP3Randomizer.Tests;

// T16: Archipelago placeholder item, "display only" switch (--ap-mode) and missile-required off (SPEC E10, E14, E15).
public class ApModeTests
{
    private static readonly byte[] NoItem = [255, 255, 255, 255];
    private static readonly byte[] Zero = [0, 0, 0, 0];
    private static readonly byte[] ItemTypeProperty = [160, 46, 240, 196];
    private static readonly byte[] CapacityProperty = [40, 199, 27, 84];
    private static readonly byte[] AmountProperty = [148, 175, 20, 69];
    private static readonly byte[] ModelProperty = [194, 127, 250, 143];
    private const string Wheel = MP3Permalink.rot_wheel;

    private static string[] BaseArgs(params string[] extra) =>
    [
        "--input-path", "in", "--output-path", "out", "--layout", "SEED", .. extra,
    ];

    private static string Permalink(string items)
    {
        string body = "00" + items;
        string sha = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(body)));
        return body + sha.Substring(0, 5).ToLowerInvariant();
    }

    private static byte[] Value(ScriptObjectModificationPatch patch, byte[] property_id)
    {
        PropertyModification modification = patch.property_modifications.Single(m => m.property_id.SequenceEqual(property_id));
        return modification.get_property_value([], 0);
    }

    [Fact]
    public void ApMode_IsOffByDefault()
    {
        Configuration configuration = Configuration.get_configuration(BaseArgs("--require-launcher", "--require-ship-missile"));

        Assert.False(configuration.ap_mode);
        Assert.True(configuration.require_launcher);
        Assert.True(configuration.require_ship_missile);
    }

    [Theory]
    [InlineData("--ap-mode", "--require-launcher", "--require-ship-missile")]
    [InlineData("--require-launcher", "--require-ship-missile", "-ap-mode")]
    public void ApMode_TurnsMissileRequiredOff(params string[] flags)
    {
        Configuration configuration = Configuration.get_configuration(BaseArgs(flags));

        Assert.True(configuration.ap_mode);
        Assert.False(configuration.require_launcher);
        Assert.False(configuration.require_ship_missile);
    }

    [Fact]
    public void ApItem_GivesNothingAndUsesOwnText()
    {
        Item item = Item.get_item_data(ItemName.APItem);

        Assert.Equal(NoItem, item.item_type);
        Assert.Equal(Zero, item.amount);
        Assert.Equal(Zero, item.capacity);
        Assert.False(item.is_progressive);
        Assert.Empty(item.conversion_start_ids);
        Assert.Empty(item.conversion_end_ids);
        Assert.Equal(0xABCDABCDABCD000Aul, Conversion.b_to_u64(item.memo));
        Assert.Equal(Item.get_item_data(ItemName.Fuse1).model, item.model);
    }

    [Fact]
    public void ApItem_TextAndDependencyAreRegistered()
    {
        STRGModification modification = STRGModificationData.get_strg_modifications(false, "", "")
            .Single(m => m.resource_id == Item.AP_ITEM_MEMO_ID);

        Assert.Equal(["Archipelago-Item"], modification.language_modifications.Single().strings);
        Assert.Equal(Language.English, modification.language_modifications.Single().language);
        Assert.Empty(MP3Dependencies.get_file_dependencies()[Item.AP_ITEM_MEMO_ID]);
    }

    [Fact]
    public void Decoder_MapsLetterAToApItem()
    {
        ItemName[] items = MP3Permalink.decode_permalink(Permalink("1A4"));

        Assert.Equal([ItemName.PlasmaBeam, ItemName.APItem, ItemName.MissileExpansion], items);
    }

    [Fact]
    public void Decoder_LetterAIsInTheRotationWheel()
    {
        Assert.Contains('A', Wheel);
    }

    [Theory]
    [InlineData(ItemName.PlasmaBeam)]
    [InlineData(ItemName.ProgressiveBeam)]
    [InlineData(ItemName.MainRequiredMissileExpansion)]
    [InlineData(ItemName.ConverterMissileLauncher)]
    [InlineData(ItemName.Fuse3)]
    public void DisplayOnly_KeepsVisualsButGivesNothing(ItemName name)
    {
        Item original = Item.get_item_data(name);
        Item item = Item.get_item_data(name);

        PickupPatches.apply_display_only(item);

        Assert.Equal(NoItem, item.item_type);
        Assert.Equal(Zero, item.amount);
        Assert.Equal(Zero, item.capacity);
        Assert.False(item.is_progressive);
        Assert.Empty(item.progressive_ids);
        Assert.Empty(item.conversion_start_ids);
        Assert.Empty(item.conversion_end_ids);
        Assert.Equal(original.model, item.model);
        Assert.Equal(original.character, item.character);
        Assert.Equal(original.scan, item.scan);
        Assert.Equal(original.memo, item.memo);
        Assert.Equal(original.streamed_audio, item.streamed_audio);
    }

    private static Patches PickupPatchesFor(ItemName name, bool display_only)
    {
        PickupLocation[] locations = PickupLocations.get_pickup_locations();
        ItemName[] items = Enumerable.Repeat(name, locations.Length).ToArray();
        Patches patches = new Patches();
        PickupPatches.add_pickup_patches(patches, locations, items, false, false, MP3Dependencies.get_file_dependencies(), display_only);
        return patches;
    }

    [Fact]
    public void DisplayOnly_WritesNoItemToEveryPickupIncludingSpecialFunctionLocations()
    {
        PickupLocation[] locations = PickupLocations.get_pickup_locations();
        Patches patches = PickupPatchesFor(ItemName.ProgressiveBeam, display_only: true);

        List<ScriptObjectModificationPatch> pickups = patches.object_modification_patches
            .Where(p => p.script_types.SequenceEqual(["PCKP"]))
            .ToList();
        int special = locations.Count(l => l.item_index != 0 && l.type == "SpecialFunction");
        Assert.Equal(10, special); // 9, 34, 42, 43, 62, 70, 73, 79, 89, 93
        Assert.Equal(99, pickups.Count);
        Assert.All(pickups, p =>
        {
            Assert.Equal(NoItem, Value(p, ItemTypeProperty));
            Assert.Equal(Zero, Value(p, AmountProperty));
            Assert.Equal(Zero, Value(p, CapacityProperty));
        });

        // SpecialFunction: the second PCKP (percentage_pickup_id) carries the item fields.
        foreach (PickupLocation location in locations.Where(l => l.item_index != 0 && l.type == "SpecialFunction"))
        {
            ScriptObjectModificationPatch pickup = pickups.Single(p =>
                p.mrea_ids[0] == location.mrea_id && p.object_ids[0] == Conversion.b_to_u16(location.percentage_pickup_id));
            Assert.Equal(NoItem, Value(pickup, ItemTypeProperty));
        }

        // Progressive beam would normally add relays and inventory givers; display only adds none.
        Assert.Empty(patches.object_addition_patches);
        Assert.Empty(patches.connection_addition_patches);
    }

    [Fact]
    public void WithoutDisplayOnly_PickupsStillGiveTheirItem()
    {
        Patches patches = PickupPatchesFor(ItemName.PlasmaBeam, display_only: false);

        List<ScriptObjectModificationPatch> pickups = patches.object_modification_patches
            .Where(p => p.script_types.SequenceEqual(["PCKP"]))
            .ToList();
        Assert.Equal(99, pickups.Count);
        Assert.All(pickups, p => Assert.Equal(new byte[] { 147, 173, 109, 249 }, Value(p, ItemTypeProperty)));
    }

    [Theory]
    [InlineData(ItemName.ChargeUpgrade)]
    [InlineData(ItemName.Bomb)]
    [InlineData(ItemName.SpaceJump)]
    [InlineData(ItemName.MorphBall)]
    public void StartingItemPickup_KeepsItsCharacterAndScan(ItemName name)
    {
        Item item = Item.get_item_data(name);
        Patches patches = PickupPatchesFor(name, display_only: true);
        foreach (PickupLocation location in PickupLocations.get_pickup_locations().Where(l => l.type == "Pickup"))
        {
            var dependencies = patches.dependency_patches[location.mrea_id];
            Assert.Contains(dependencies, d => d.file_id == Conversion.b_to_u64(item.character));
            Assert.Contains(dependencies, d => d.file_id == Conversion.b_to_u64(item.scan));
        }
    }

    [Fact]
    public void BombScan_LoadsItsLogbookTextAndTextures()
    {
        var dependencyTable = MP3Dependencies.get_file_dependencies();
        var dependencies = MP3Dependencies.get_dependencies_of(dependencyTable,
            Conversion.b_to_u64(Item.get_item_data(ItemName.Bomb).scan), "SCAN");

        Assert.Contains(dependencies, d => d.file_id == 0xF0E00E2A0B4E39AEul);
        Assert.Contains(dependencies, d => d.file_id == 0x8535E6856636FCBEul);
        Assert.Contains(dependencies, d => d.file_id == 0x1153AC25599D7FABul);
        Assert.Contains(dependencies, d => d.file_id == 0x7A474E0EBC7A47D4ul);
        var scanText = MP3Dependencies.get_dependencies_of(dependencyTable, 0xF0E00E2A0B4E39AEul, "STRG");
        Assert.Contains(scanText, d => d.file_id == 0xAB07101E7F8CF492ul);
    }

    [Fact]
    public void ApItemPickup_UsesStaticModel()
    {
        Patches patches = PickupPatchesFor(ItemName.APItem, display_only: false);

        ScriptObjectModificationPatch pickup = patches.object_modification_patches
            .First(p => p.script_types.SequenceEqual(["PCKP"]) && p.property_modifications.Length == 7);
        Assert.Equal(NoItem, Value(pickup, ItemTypeProperty));
        Assert.Equal(Item.get_item_data(ItemName.APItem).model, Value(pickup, ModelProperty));
        Assert.Contains(patches.dependency_patches.Values.SelectMany(d => d), d => d.file_id == Item.AP_ITEM_MEMO_ID);
    }
}
