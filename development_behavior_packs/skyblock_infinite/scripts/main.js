/**
 * Skyblock Infinite for Bedrock: island generation and the config menu.
 *
 * The Java datapack does this with a void dimension, scoreboards and a menu built out of block_display and
 * interaction entities. Bedrock has none of those, so the void comes from the world itself (a flat world with
 * no block layers, see tools/build_world.py), the scoreboards become world dynamic properties, and the menu
 * becomes a real Bedrock form.
 *
 * Placement mirrors java/data/skyblock/functions exactly: the same structures at the same coordinates, the
 * player at 6 64 6. A structure only loads into chunks the server has loaded, which is why each island gets a
 * ticking area for a moment first, the way the datapack forceloads a chunk before `place template`.
 */
import { ItemStack, system, world } from "@minecraft/server";
import { ActionFormData } from "@minecraft/server-ui";
import { FALLBACK, ISLANDS, NETHER, OUTER, STARTING } from "./islands.js";

/** Where the datapack puts the player once the starting island is down. */
const SPAWN = { x: 6, y: 64, z: 6 };
/** Dynamic properties stand in for the datapack's scoreboards. */
const PROP = {
    generated: "sbi:generated",     // the starting island is down
    configured: "sbi:configured",   // the player has finished the menu
    seed: "sbi:seed",               // picks the island layout; see pickStarting
    main: "sbi:main",               // "seed" | "classic" | a starting island name
    outer: "sbi:outer",             // "seed" | "classic" | "off"
    nether: "sbi:nether",           // "on" | "off"
    portal: "sbi:portal",           // "far" | "near" | "off"
};
/** How long a ticking area needs before its chunks are really loaded. Measured on the server: a nether
 * chunk was still unloaded half a second after the area was added and loaded by a second and a half. */
const HOLD_TICKS = 40;
/** The end portal room, which Bedrock cannot generate in a void the way Java's strongholds do. */
const PORTAL_SPOT = { far: { x: 1000, y: 60, z: 1000 }, near: { x: 64, y: 60, z: 64 } };
/** Cracked and mossy bricks on the portal room's inside walls, offset from its middle, so the room looks
 * like a stronghold rather than a box. Fixed rather than random, so every world's room is the same. */
const WEATHERING = [
    [-5, 0, -3, "cracked"], [-5, 2, 1, "mossy"], [-5, 3, -4, "cracked"], [-4, 0, 5, "mossy"],
    [-3, 1, -5, "mossy"], [-2, 3, 5, "cracked"], [-1, 0, -5, "cracked"], [0, 2, 5, "mossy"],
    [1, 4, -5, "cracked"], [2, 0, 5, "cracked"], [3, 1, 5, "mossy"], [3, 3, -5, "mossy"],
    [5, 0, -2, "mossy"], [5, 1, 3, "cracked"], [5, 3, 0, "cracked"], [5, 4, -4, "mossy"],
    [-4, -1, -4, "cracked"], [4, -1, 4, "mossy"], [-4, -1, 4, "mossy"], [4, -1, -4, "cracked"],
];

const overworld = () => world.getDimension("overworld");
const nether = () => world.getDimension("nether");

/** A small deterministic hash, so one layout seed always picks the same islands. */
function hash(text) {
    let value = 2166136261;
    for (let i = 0; i < text.length; i++) {
        value ^= text.charCodeAt(i);
        value = Math.imul(value, 16777619);
    }
    return value >>> 0;
}

function getProp(key, fallback) {
    const value = world.getDynamicProperty(key);
    return value === undefined ? fallback : value;
}

/** The layout seed, minted once per world. `/scriptevent sbi:seed <n>` sets it before generation. */
function layoutSeed() {
    let seed = world.getDynamicProperty(PROP.seed);
    if (seed === undefined) {
        seed = String(Math.floor(Math.random() * 2147483647));
        world.setDynamicProperty(PROP.seed, seed);
    }
    return seed;
}

/**
 * Which starting island a world gets. The datapack samples the biome the player is standing in, which a
 * Bedrock void world cannot offer: a flat world is one biome everywhere. So seed mode picks from the layout
 * seed instead, which keeps what the mode is for - a different island every world - and classic mode gives
 * the plains island the original Skyblock always started on.
 */
function pickStarting(mode, seed) {
    if (mode === "classic") return FALLBACK;
    if (STARTING.includes(mode)) return mode;
    return STARTING[hash(seed) % STARTING.length];
}

/** The islands still to place, worked through one at a time by startQueue. */
const queue = [];
let queueRunner;

/**
 * One placement, looked up in the generated island table. Nothing builds a structure name by hand: the name
 * is `skyblock:<kind>_<name>` rather than the datapack's `skyblock:<kind>/<name>`, because `/structure load`
 * refuses a `/` in a structure name, and islands.js is the one place that knows it.
 */
function job(key, dimension, label) {
    const island = ISLANDS[key];
    if (!island || !island.offset) return undefined;
    const [x, y, z] = island.offset;
    return { structure: island.structure, dimension, x, y, z, label: label ?? key };
}

function enqueue(key, dimension, label) {
    const next = job(key, dimension, label);
    if (next) queue.push(next);
}

const dimensionOf = (task) => (task.dimension === "nether" ? nether() : overworld());
const areaOf = (task) => `sbi_${task.dimension}_${Math.abs(task.x)}_${Math.abs(task.z)}`;

function run(dimension, command) {
    try {
        return dimension.runCommand(command);
    } catch {
        return undefined;       // the chunk is not held, or a ticking area by that name is already there
    }
}

/**
 * Ask the server to hold an island's chunks. `/structure load` into a chunk nobody has loaded reports
 * success and places nothing, which is how four nether islands came back empty the first time this was
 * tested: adding the ticking area and loading in the same tick is too early. The chunks need about two
 * seconds, so holding and loading are two steps, HOLD_TICKS apart, the way the datapack forceloads a chunk
 * and schedules its `place template` for twenty ticks later.
 */
function hold(task) {
    run(dimensionOf(task), `tickingarea add circle ${task.x} ${task.y} ${task.z} 2 ${areaOf(task)}`);
}

function load(task) {
    const dimension = dimensionOf(task);
    const result = run(dimension, `structure load ${task.structure} ${task.x} ${task.y} ${task.z}`);
    if (result === undefined || result.successCount === 0) {
        world.sendMessage(`§cSkyblock Infinite could not place ${task.label}.`);
    }
    run(dimension, `tickingarea remove ${areaOf(task)}`);
    if (task.after) task.after();
}

/** Place one island on its own, holding its chunks for HOLD_TICKS first. */
function placeNow(task) {
    if (!task) return;
    hold(task);
    system.runTimeout(() => load(task), HOLD_TICKS);
}

/** Work through the queue: hold one island's chunks, place it once they are loaded, move on. */
function startQueue() {
    if (queueRunner !== undefined) return;
    let pending;
    let countdown = 0;
    queueRunner = system.runInterval(() => {
        if (pending) {
            if (countdown-- > 0) return;
            load(pending);
            pending = undefined;
            return;
        }
        const next = queue.shift();
        if (!next) {
            system.clearRun(queueRunner);
            queueRunner = undefined;
            world.sendMessage("§aIsland placement finished. Have fun!");
            return;
        }
        hold(next);
        pending = next;
        countdown = HOLD_TICKS / 5;
    }, 5);
}

/**
 * The starting island, the spawn point and the first look at the menu. The spawn is moved and the players
 * are put on the island only once it is actually down: placing is two steps now, and teleporting into the
 * gap between them drops everyone into the void.
 */
function generateStartingIsland() {
    const seed = layoutSeed();
    const name = pickStarting(getProp(PROP.main, "seed"), seed);
    const task = job(`starting_islands/${name}`, "overworld", `the ${name} island`);
    task.after = () => {
        run(overworld(), `setworldspawn ${SPAWN.x} ${SPAWN.y} ${SPAWN.z}`);
        for (const player of world.getAllPlayers()) {
            player.teleport(SPAWN, { dimension: overworld() });
            run(player, `spawnpoint @s ${SPAWN.x} ${SPAWN.y} ${SPAWN.z}`);
        }
        world.sendMessage(`§eYour island is a §f${name.replace(/_/g, " ")}§e island. Layout seed §f${seed}§e.`);
    };
    placeNow(task);
    world.setDynamicProperty(PROP.generated, true);
}

/** The outer ring, the nether ring and the end portal, from the choices the menu stored. */
function generateWorld() {
    const outer = getProp(PROP.outer, "seed");
    const seed = layoutSeed();
    if (outer !== "off") {
        // Classic places all sixteen. Seed mode places the eight of the inner ring that the seed picks,
        // because the datapack's seed mode only ever places an island once it finds the matching biome.
        const chosen = outer === "classic" ? OUTER : OUTER.filter((_, i) => (hash(seed + i) & 1) === 0);
        world.sendMessage(`§eIsland placement started (${chosen.length} outer islands). This takes a few seconds.`);
        for (const name of chosen) enqueue(`outer_islands/${name}`, "overworld", `the ${name} outer island`);
    }
    if (getProp(PROP.nether, "off") === "on") {
        for (const name of NETHER) enqueue(`nether_islands/${name}`, "nether", `the ${name} nether island`);
    }
    const portal = getProp(PROP.portal, "far");
    if (portal !== "off") buildEndPortal(PORTAL_SPOT[portal]);
    world.setDynamicProperty(PROP.configured, true);
    startQueue();
}

/**
 * A stronghold portal room floating in the void. Java's datapack leaves this to vanilla worldgen, which
 * generates strongholds in its void dimension; a Bedrock flat world generates no structures at all, so
 * without this the End is unreachable. The room is the vanilla twelve-frame portal in a stone brick shell,
 * with the eyes left out so it still has to be finished with ender eyes.
 */
function buildEndPortal(spot) {
    const d = overworld();
    const { x, y, z } = spot;
    run(d, `tickingarea add circle ${x} ${y} ${z} 2 sbi_portal`);
    // the same two steps a structure needs: the room is a thousand blocks from spawn, so its chunks have to
    // be held and given time before a fill will write anything into them
    system.runTimeout(() => {
        // the shell, then the room hollowed out of it
        run(d, `fill ${x - 6} ${y - 2} ${z - 6} ${x + 6} ${y + 5} ${z + 6} stonebrick`);
        run(d, `fill ${x - 5} ${y} ${z - 5} ${x + 5} ${y + 4} ${z + 5} air`);
        // the weathering a real stronghold has, so the room does not read as a plain box
        for (const [sx, sy, sz, kind] of WEATHERING) {
            run(d, `setblock ${x + sx} ${y + sy} ${z + sz} stonebrick ["stone_brick_type"="${kind}"]`);
        }
        // the lava the vanilla portal room sits over
        run(d, `fill ${x - 2} ${y - 1} ${z - 2} ${x + 2} ${y - 1} ${z + 2} lava`);
        run(d, `fill ${x - 1} ${y - 1} ${z - 1} ${x + 1} ${y - 1} ${z + 1} stonebrick`);
        // a way in, so nobody has to mine through the shell to find out whether this worked
        run(d, `fill ${x} ${y} ${z - 6} ${x} ${y + 1} ${z - 6} air`);
        run(d, `fill ${x - 1} ${y - 1} ${z - 7} ${x + 1} ${y - 1} ${z - 6} stonebrick`);
        // the twelve frames, each facing the middle, with the eyes left out so the portal still has to be
        // finished with ender eyes
        for (let i = -1; i <= 1; i++) {
            run(d, `setblock ${x + i} ${y} ${z - 2} end_portal_frame ["minecraft:cardinal_direction"="south"]`);
            run(d, `setblock ${x + i} ${y} ${z + 2} end_portal_frame ["minecraft:cardinal_direction"="north"]`);
            run(d, `setblock ${x - 2} ${y} ${z + i} end_portal_frame ["minecraft:cardinal_direction"="east"]`);
            run(d, `setblock ${x + 2} ${y} ${z + i} end_portal_frame ["minecraft:cardinal_direction"="west"]`);
        }
        run(d, `fill ${x - 1} ${y} ${z - 1} ${x + 1} ${y} ${z + 1} air`);
        run(d, `tickingarea remove sbi_portal`);
        world.sendMessage(`§eA stronghold portal room is waiting at §f${x} ${y} ${z}§e. Bring twelve ender eyes.`);
    }, HOLD_TICKS);
}

// ---------------------------------------------------------------------------
// The config menu
// ---------------------------------------------------------------------------
//
// The Java datapack builds this menu in the world: four block_display blocks floating over the island that
// you punch to cycle a setting, and a fifth to start. Bedrock has no block displays or interaction entities,
// and punching a block in mid air is the one kind of menu a controller is worst at.
//
// So every setting is a list of buttons instead of a dropdown. A button list is what a gamepad can drive
// with nothing but the stick and A; a dropdown needs a pointer to open it and scroll it, which is why the
// first version of this menu was awkward on a controller. Each button carries a picture of what it gives
// you - the island previews under textures/ui/islands/, which are real screenshots of the real islands,
// taken by tools/capture_previews.py.

/** A preview texture. Every one of these is a file in the resource pack; nothing here is a vanilla path. */
const ICON = (name) => `textures/ui/islands/${name}`;
const ICON_OFF = ICON("void");          // a picture of the empty void, which is what Off leaves you with
const ICON_PORTAL = ICON("portal_room");
const ICON_START = ICON("spawn");

// The data pack's own file names, a couple of which are misspelled. The menu shows them as they are meant
// to read; on disk they stay exactly as they are, because the structure names have to keep matching.
const LABELS = { crimpson_forest: "Crimson Forest", plaines: "Plains", taiga_snow: "Snowy Taiga",
                 windswept_gravel_hills: "Windswept Gravelly Hills" };
const pretty = (name) => LABELS[name] ?? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/**
 * The settings, in the order the menu lists them. `choices` are the buttons inside a setting; `icon` may be
 * a function so a choice can show what this particular world would give (seed mode shows the island this
 * world's seed actually picked).
 */
function settings() {
    const seedIsland = pickStarting("seed", layoutSeed());
    return [
        {
            prop: PROP.main, title: "Starting island", fallback: "seed",
            describe: (value) => (STARTING.includes(value) ? pretty(value) : value === "classic" ? "Classic" : "Seed"),
            icon: (value) => ICON(`starting_islands_${STARTING.includes(value) ? value : value === "classic" ? FALLBACK : seedIsland}`),
            choices: [
                { value: "seed", label: "Seed", hint: `This world's seed gives the ${pretty(seedIsland)} island`,
                  icon: ICON(`starting_islands_${seedIsland}`) },
                { value: "classic", label: "Classic", hint: "The original plains island",
                  icon: ICON(`starting_islands_${FALLBACK}`) },
                { value: "pick", label: "Choose one", hint: `Pick from all ${STARTING.length} islands`,
                  icon: ICON("starting_islands_cherry_grove") },
            ],
        },
        {
            prop: PROP.outer, title: "Outer islands", fallback: "seed",
            describe: (value) => ({ seed: "Seed", classic: "Classic", off: "Off" }[value] ?? value),
            icon: (value) => ({ seed: ICON("outer_islands_jungle"), classic: ICON("outer_islands_cherry_grove"),
                                off: ICON_OFF }[value] ?? ICON_OFF),
            choices: [
                { value: "seed", label: "Seed", hint: "The islands this world's seed picks",
                  icon: ICON("outer_islands_jungle") },
                { value: "classic", label: "Classic", hint: "All sixteen, in the classic rings",
                  icon: ICON("outer_islands_cherry_grove") },
                { value: "off", label: "Off", hint: "No outer islands", icon: ICON_OFF },
            ],
        },
        {
            prop: PROP.nether, title: "Nether islands", fallback: "off",
            describe: (value) => (value === "on" ? "On" : "Off"),
            icon: (value) => (value === "on" ? ICON("nether_islands_crimson_forest") : ICON_OFF),
            choices: [
                { value: "off", label: "Off", hint: "Bedrock generates a normal Nether already", icon: ICON_OFF },
                { value: "on", label: "On", hint: "Place the five nether islands as well",
                  icon: ICON("nether_islands_crimson_forest") },
            ],
        },
        {
            prop: PROP.portal, title: "End portal", fallback: "far",
            describe: (value) => ({ far: "Far", near: "Near", off: "Off" }[value] ?? value),
            icon: (value) => (value === "off" ? ICON_OFF : ICON_PORTAL),
            choices: [
                { value: "far", label: "Far", hint: "A stronghold portal room at 1000 60 1000", icon: ICON_PORTAL },
                { value: "near", label: "Near", hint: "One at 64 60 64", icon: ICON_PORTAL },
                { value: "off", label: "Off", hint: "No end portal", icon: ICON_OFF },
            ],
        },
    ];
}

/**
 * Show a form, retrying while the player is still busy closing the last one. Chaining forms is the whole
 * shape of this menu, and a form shown in the same tick another closed is simply refused.
 */
async function show(form, player) {
    for (let attempt = 0; attempt < 20; attempt++) {
        const response = await form.show(player);
        if (response.cancelationReason !== "UserBusy") return response;
        await system.waitTicks(10);
    }
    return { canceled: true };
}

/** The hub: one button per setting showing what it is set to, then Start. */
async function showConfig(player) {
    const model = settings();
    const form = new ActionFormData()
        .title("Skyblock Infinite")
        .body(`Layout seed: §7${layoutSeed()}§r\nPick what this world should be, then press Start.`);
    for (const setting of model) {
        const value = getProp(setting.prop, setting.fallback);
        form.button(`${setting.title}\n${setting.describe(value)}`, setting.icon(value));
    }
    form.button("Start", ICON_START);
    const response = await show(form, player);
    if (response.canceled) return;
    if (response.selection === model.length) return applyAndStart(player);
    const setting = model[response.selection];
    if (setting.prop === PROP.main) await showMainChoice(player, setting);
    else await showChoice(player, setting);
    return showConfig(player);
}

/** One setting's choices, as buttons with their pictures. */
async function showChoice(player, setting) {
    const form = new ActionFormData().title(setting.title).body("Choose one.");
    for (const choice of setting.choices) form.button(`${choice.label}\n${choice.hint}`, choice.icon);
    form.button("Back");
    const response = await show(form, player);
    if (response.canceled || response.selection >= setting.choices.length) return;
    world.setDynamicProperty(setting.prop, setting.choices[response.selection].value);
}

/** The starting island, where "Choose one" opens the picker. */
async function showMainChoice(player, setting) {
    const form = new ActionFormData().title(setting.title).body("Choose one.");
    for (const choice of setting.choices) form.button(`${choice.label}\n${choice.hint}`, choice.icon);
    form.button("Back");
    const response = await show(form, player);
    if (response.canceled || response.selection >= setting.choices.length) return;
    const choice = setting.choices[response.selection];
    if (choice.value === "pick") return showIslandPicker(player, setting);
    world.setDynamicProperty(setting.prop, choice.value);
}

/** Every starting island, each with its own picture. The datapack has no such screen: it only ever picks
 * for you. The previews make choosing worth offering, and it is the one place a 26 item list earns itself. */
async function showIslandPicker(player, setting) {
    const form = new ActionFormData().title("Starting island")
        .body("Every island the data pack ships. The chest on each one is the same.");
    for (const name of STARTING) form.button(pretty(name), ICON(`starting_islands_${name}`));
    form.button("Back");
    const response = await show(form, player);
    if (response.canceled) return;
    if (response.selection >= STARTING.length) return showMainChoice(player, setting);
    world.setDynamicProperty(setting.prop, STARTING[response.selection]);
}

/** Start: store nothing new, swap the island if the choice differs from what is already down, and generate. */
function applyAndStart(player) {
    const wanted = getProp(PROP.main, "seed");
    const placed = pickStarting(wanted, layoutSeed());
    // The island already placed was picked by the seed. If the player chose differently, the old one is
    // cleared and the new one goes down, the way the datapack's replace_island_with_plaines does.
    if (placed !== pickStarting("seed", layoutSeed())) {
        // every starting island fits inside 0 57 2 to 13 75 16, with a block of margin either way
        run(overworld(), "fill -1 56 1 14 76 17 air");
        const swap = job(`starting_islands/${placed}`, "overworld", `the ${placed} island`);
        swap.after = () => {
            for (const p of world.getAllPlayers()) p.teleport(SPAWN, { dimension: overworld() });
        };
        placeNow(swap);
    }
    generateWorld();
}

/** Reopening the menu after the world is set up only offers what can still be changed. */
async function showMenu(player) {
    if (!world.getDynamicProperty(PROP.configured)) return showConfig(player);
    const form = new ActionFormData().title("Skyblock Infinite")
        .body(`Layout seed: §7${layoutSeed()}§r\nStarting island: §7${getProp(PROP.main, "seed")}§r\nOuter islands: §7${getProp(PROP.outer, "seed")}§r`)
        .button("Place the outer islands again", ICON("outer_islands_jungle"))
        .button("Place the nether islands", ICON("nether_islands_crimson_forest"))
        .button("Build an end portal room here", ICON_PORTAL)
        .button("Close");
    const response = await show(form, player);
    if (response.canceled || response.selection === 3) return;
    if (response.selection === 0) {
        for (const name of OUTER) enqueue(`outer_islands/${name}`, "overworld", `the ${name} outer island`);
        startQueue();
    } else if (response.selection === 1) {
        for (const name of NETHER) enqueue(`nether_islands/${name}`, "nether", `the ${name} nether island`);
        startQueue();
    } else {
        const at = player.location;
        buildEndPortal({ x: Math.floor(at.x), y: Math.floor(at.y), z: Math.floor(at.z) });
    }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

/** The datapack waits for a player before placing anything, so that a server generates nothing into an
 * empty world; this does the same. */
function onReady() {
    if (!world.getDynamicProperty(PROP.generated)) {
        if (world.getAllPlayers().length === 0) return false;
        generateStartingIsland();
    }
    return true;
}

system.runInterval(() => { onReady(); }, 20);

world.afterEvents.playerSpawn.subscribe((event) => {
    if (!event.initialSpawn) return;
    system.runTimeout(() => {
        if (!onReady()) return;
        if (!world.getDynamicProperty(PROP.configured)) showMenu(event.player);
        event.player.sendMessage("§7Skyblock Infinite: open the menu any time with §f/scriptevent sbi:menu§7.");
    }, 40);
});

/**
 * The husk's sand, from java/data/minecraft/loot_tables/entities/husk.json: half the husks killed drop a
 * block of sand, which is how a skyblock gets sand at all. It is dropped from here rather than from a loot
 * table because a Bedrock husk rolls loot_tables/entities/zombie.json, the same file a zombie rolls, so an
 * override would hand every zombie sand too. The coral and the ancient debris do have tables of their own
 * and are in loot_tables/entities/.
 */
world.afterEvents.entityDie.subscribe((event) => {
    const dead = event.deadEntity;
    if (dead?.typeId !== "minecraft:husk" || Math.random() >= 0.5) return;
    try {
        dead.dimension.spawnItem(new ItemStack("minecraft:sand", 1), dead.location);
    } catch { /* the chunk went out from under it */ }
}, { entityTypes: ["minecraft:husk"] });

system.afterEvents.scriptEventReceive.subscribe((event) => {
    const player = event.sourceEntity;
    if (event.id === "sbi:menu" && player) showMenu(player);
    // Reopen the setup menu on a world that is already set up, so the choices can be made again. The
    // islands already placed are left where they are; Start puts down whatever the new choices ask for.
    if (event.id === "sbi:reconfigure" && player) {
        world.setDynamicProperty(PROP.configured, false);
        showConfig(player);
    }
    if (event.id === "sbi:seed" && !world.getDynamicProperty(PROP.generated)) {
        world.setDynamicProperty(PROP.seed, event.message.trim());
        world.sendMessage(`§eLayout seed set to §f${event.message.trim()}§e.`);
    }
    if (event.id === "sbi:island" && event.message.trim()) {
        const name = event.message.trim();
        if (!STARTING.includes(name)) {
            world.sendMessage(`§cNo starting island called ${name}. One of: ${STARTING.join(", ")}`);
            return;
        }
        placeNow(job(`starting_islands/${name}`, "overworld", `the ${name} island`));
    }
}, { namespaces: ["sbi"] });
