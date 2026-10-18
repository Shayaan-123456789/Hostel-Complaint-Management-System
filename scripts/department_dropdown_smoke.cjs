/* Node smoke test: the Add/Edit Staff departments are live select lists.
 * Exercises real UI code with mocked APIs. No Oracle calls or writes. */
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('node:assert/strict');
const script=fs.readFileSync(path.join(__dirname,'../hostel/static/hostel/app.js'),'utf8');
const events={};
const root={innerHTML:'',addEventListener:(type,fn)=>{events[type]=fn;}};
const toast={innerHTML:''};
const modal={innerHTML:'',querySelector:()=>({focus(){}})};
const document={querySelector:s=>s==='#root'?root:s==='#toast'?toast:s==='#modalMount'?modal:null};
const storage={getItem:()=>null,setItem(){},removeItem(){}};
let cats=[{category_id:1,category_name:'Electrical'},{category_id:2,category_name:'Plumbing'}];
let categoryCalls=0;
const user={role:'WARDEN',id:'warden',name:'warden'};
const fixture={
  '/api/auth/login/': {access_token:'fake-token',user},
  '/api/admin/dashboard/':{totals:{total_complaints:0,pending:0,resolved:0},by_category_status:[]},
  '/api/complaints/summary/':{summary:{total:0,open_count:0}},
  '/api/complaints/':{total:0,complaints:[]},
  '/api/admin/staff/':{staff:[{staff_id:1,name:'Ravi Electrician',email:'ravi@hostel.edu',department:'Electrical',status:'ACTIVE',active_assignments:0}]}
};
const fetch=async url=>{
 const endpoint=url.split('?')[0];
 if(endpoint==='/api/categories/') {categoryCalls++;return {ok:true,status:200,json:async()=>({categories:cats})};}
 if(!(endpoint in fixture))throw Error('Unexpected request '+endpoint);
 return {ok:true,status:200,json:async()=>fixture[endpoint]};
};
class FakeFormData {constructor(form){this.entries=()=>Object.entries(form.values||{})}}
const context={document,sessionStorage:storage,fetch,FormData:FakeFormData,
  setTimeout,clearTimeout,URL,URLSearchParams,window:{open(){}},console};
vm.createContext(context);vm.runInContext(script,context);
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
const click=async(action,id,view)=>events.click({target:{dataset:{action,id,view},closest(){return this;}},preventDefault(){}});
(async()=>{
 await tick();
 await events.submit({target:{id:'authForm',values:{username:'warden',password:'pass'},querySelector:()=>({disabled:false})},preventDefault(){}});
 await tick();
 // Overview shortcut must fetch categories, even before visiting Categories page.
 await click('new-staff');
 assert.match(modal.innerHTML,/<select name="department" required>/);
 assert.match(modal.innerHTML,/<option value="Electrical"/);
 assert.match(modal.innerHTML,/<option value="Plumbing"/);
 assert.doesNotMatch(modal.innerHTML,/<input name="department"/);
 assert.equal(categoryCalls,1);
 // A category created after the first form load must be available next time.
 cats=[...cats,{category_id:3,category_name:'Internet'}];
 await click('new-staff');
 assert.match(modal.innerHTML,/<option value="Internet"/);
 assert.equal(categoryCalls,2);
 // Edit Staff uses same dropdown with current department preselected.
 await click('navigate',null,'staff');
 await click('edit-staff','1');
 assert.match(modal.innerHTML,/<option value="Electrical" selected>Electrical<\/option>/);
 assert.equal(categoryCalls,3);
 assert.doesNotMatch(modal.innerHTML,/<input name="department"/);
 // Empty category list gives an actionable message, not an editable text box.
 cats=[];
 await click('new-staff');
 assert.match(toast.innerHTML,/Create a complaint category/);
 console.log('PASS: overview Add Staff dropdown, fresh categories, edit preselection, empty categories');
})().catch(e=>{console.error(e);process.exitCode=1;});
