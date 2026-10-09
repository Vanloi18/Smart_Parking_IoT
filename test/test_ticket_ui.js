// Mock DOM/fetch: kiểm tra chi tiết vé và thao tác lưu, không gọi backend thật.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.value = ''; this.open = false; }
    appendChild(child) { this.children.push(child); }
    replaceChildren() { this.children = []; }
    setAttribute(name, value) { this[name] = value; }
    showModal() { this.open = true; }
    close() { this.open = false; }
}
const body = new Element('body');
const select = new Element('select');
let session = {id:13, rfid_uid:'TEST_UID', status:'PARKED', plate_number:'59X1-123.45',
    plate_source:'OCR', needs_plate:1, entry_image_url:'/uploads/entry.jpg', exit_image_url:'/uploads/exit.jpg', fee:0};
let writes = 0;
const context = {document:{body, createElement:tag=>new Element(tag), getElementById:()=>select},
    API_BASE:'http://example.test', getAuthHeader:()=>({}), fetchFullStatus:async()=>{},
    fetch:async(url, options={})=> {
        if (options.method === 'PATCH') {
            writes++;
            session = {...session, plate_number:JSON.parse(options.body).plate, plate_source:'MANUAL', needs_plate:0};
            return {ok:true,json:async()=>({status:'success'})};
        }
        return {ok:true,json:async()=>({session})};
    }};
vm.createContext(context);
const source = fs.readFileSync('dashboard/frontend/js/app.js','utf8');
vm.runInContext(source.slice(source.indexOf('let ticketDialog = null;')), context);
function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }
(async()=> {
    context.renderTicketSelector([session]);
    assert(select.children[0].textContent.includes('TEST_UID'));
    await context.showTicketSessionDetail(13);
    let nodes = descendants(body);
    assert.equal(nodes.filter(node=>node.tag==='img').length,2);
    assert(nodes.some(node=>(node.textContent||'').includes('CHỜ XÁC NHẬN')));
    nodes.find(node=>node.tag==='input').value='30A-123.45';
    await nodes.find(node=>node.textContent==='Xác nhận / lưu biển số').onclick();
    assert.equal(writes,1);
    assert(descendants(body).some(node=>(node.textContent||'').includes('Nhập tay')));
    session={...session,status:'CHECKED_OUT'};
    await context.showTicketSessionDetail(13);
    nodes=descendants(body);
    assert.equal(nodes.find(node=>node.tag==='input').disabled,true);
    assert(!nodes.some(node=>node.textContent==='Xác nhận / lưu biển số'));
    console.log('PASS: paired images, confirm/manual save and closed-session read-only');
})().catch(error=>{console.error(error);process.exitCode=1;});
