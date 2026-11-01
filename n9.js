const puppeteer = require('puppeteer');

const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const dbPath = path.join('', 'hpb_inventory.db');
const db = new sqlite3.Database(dbPath);

// const db = new sqlite3.Database('./hpb_inventory.db');

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS inventory_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        title TEXT,
        price TEXT,
        usedSku TEXT,
        storeName TEXT,
        city TEXT,
        state TEXT,
        distanceMiles REAL,
        qty INTEGER
    )`);
});

async function runInventoryCheck() {
    console.log('Launching headless browser...');
    const browser = await puppeteer.launch({ headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    const page = await browser.newPage();

    await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:157.0) Gecko/20100101 Firefox/157.0');

    const searchUrl = 'https://www.hpb.com/search?q=Aoyama%2C+Gosho&prefn1=subjectLevel1&prefv1=Book';
    console.log(`Navigating to HPB search page...`);
    await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: 60000 });

    const productsMap = new Map();
    const tiles = await page.$$('.product-tile, [data-pid]');
    
    for (const tile of tiles) {
        const data = await tile.evaluate(el => {
            const pid = el.getAttribute('data-pid') || el.querySelector('[data-pid]')?.getAttribute('data-pid');
            if (!pid) return null;
            const titleEl = el.querySelector('.product-name, a.link, .pdp-link');
            const title = titleEl ? titleEl.textContent.trim() : 'Unknown Title';
            const priceEl = el.querySelector('.price .sales, .price, .sales span, .value');
            const price = priceEl ? priceEl.textContent.trim() : 'N/A';
            return { pid, title, price };
        });

        if (!data) continue;

        let cleanId = data.pid.startsWith('M-') ? data.pid.replace('M-', '').replace(/-T$/, '') : data.pid.replace(/^P-/, '').replace(/-(NEW|USED)$/, '');

        if (!productsMap.has(cleanId)) {
            productsMap.set(cleanId, {
                title: data.title,
                price: data.price,
                usedSku: `P-${cleanId}-USED`
            });
        }
    }

    const items = Array.from(productsMap.values());
    console.log(`Found ${items.length} unique items. Checking store availability...`);

    const postalCode = '75231';
    const lat = '32.879729';
    const long = '-96.744154';
    const currentTimestamp = new Date().toISOString();

    const stmt = db.prepare(`INSERT INTO inventory_logs (timestamp, title, price, usedSku, storeName, city, state, distanceMiles, qty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`);

    for (const item of items) {
        console.log(`Checking stock for: ${item.title} (${item.usedSku})`);
        const storeApiUrl = `https://www.hpb.com/on/demandware.store/Sites-hpb-Site/en_US/Stores-FindStores?showMap=false&hiddenPostalCode=${postalCode}&isFromPDPCart=true&productId=${item.usedSku}&onlyAvailableStores=true&lat=${lat}&long=${long}`;

        try {
            const storeData = await page.evaluate(async (url) => {
                const res = await fetch(url);
                if (!res.ok) return null;
                return await res.json();
            }, storeApiUrl);

            if (storeData && storeData.stores) {
                const inStockStores = storeData.stores.filter(store => 
                    store.storeDeliveryDetails && store.storeDeliveryDetails.inventorylevel > 0
                );

                inStockStores.forEach(store => {
                    let dist = parseFloat(store.distanceinMI);
                    stmt.run(
                        currentTimestamp,
                        item.title,
                        item.price,
                        item.usedSku,
                        store.name,
                        store.city,
                        store.stateCode || 'TX',
                        isNaN(dist) ? null : dist,
                        store.storeDeliveryDetails.inventorylevel
                    );
                });
            }
        } catch (err) {
            console.error(`Error checking SKU ${item.usedSku}:`, err.message);
        }
    }

    stmt.finalize();
    console.log(`Run completed and saved to database at ${currentTimestamp}`);
    await browser.close();
    db.close();
}

runInventoryCheck();
