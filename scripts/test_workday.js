const [tenant, shard, site] = process.argv.slice(2);

if (!tenant || !shard || !site) {
    console.error("Usage: node fetch_workday.js <tenant> <shard> <site>");
    process.exit(1);
}

const url = `https://${tenant}.wd${shard}.myworkdayjobs.com/wday/cxs/${tenant}/${site}/jobs`;

const headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": `https://${tenant}.wd${shard}.myworkdayjobs.com`,
    "Referer": `https://${tenant}.wd${shard}.myworkdayjobs.com/${site}`
};

const payload = {
    "appliedFacets": {},
    "limit": 20,
    "offset": 0,
    "searchText": ""
};

async function fetchJobs() {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const data = await response.json();
            console.log(JSON.stringify(data));
        } else {
            console.error(`Error: ${response.status} ${response.statusText}`);
            const text = await response.text();
            console.error(text);
            process.exit(1);
        }
    } catch (err) {
        console.error("Fetch failed:", err);
        process.exit(1);
    }
}

fetchJobs();
