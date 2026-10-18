/* Optional dependency-free UI runtime smoke test: node scripts/frontend_smoke.cjs */
const fs=require('fs');const path=require('path');const vm=require('vm');const assert=require('node:assert/strict');
const js=fs.readFileSync(path.join(__dirname,'../hostel/static/hostel/app.js'),'utf8');
const events={};const root={innerHTML:'',addEventListener:(type,cb)=>{events[type]=cb;}};
const toast={innerHTML:''};const modal={innerHTML:'',querySelector:()=>({focus(){}})};
const doc={querySelector:(sel)=>sel==='#root'?root:sel==='#toast'?toast:sel==='#modalMount'?modal:null};
const storage={getItem:()=>null,setItem(){},removeItem(){}};
const user={role:'WARDEN',id:'warden',name:'warden',email:null};
const complaint={complaint_id:1003,title:'Socket <sparking>',description:'Broken outlet',student_name:'Arun',block:'A',room_number:'101',category_name:'Electrical',status:'OPEN',priority:'URGENT',created_date:'2026-10-17T10:00:00',photos:[],history:[],assignments:[]};
const fixtures={
 '/api/auth/login/':()=>({access_token:'test-token',user}),
 '/api/auth/me/':()=>({user}),
 '/api/admin/dashboard/':()=>({totals:{total_complaints:1,pending:1,resolved:0},by_category_status:[]}),
 '/api/complaints/summary/':()=>({summary:{total:1,open_count:1}}),
 '/api/complaints/':()=>({total:1,complaints:[complaint]}),
 '/api/complaints/1003/':()=>({complaint}),
 '/api/admin/staff/':()=>({staff:[{staff_id:3,name:'Ravi',status:'ACTIVE',email:'ravi@hostel.edu',active_assignments:0}]}),
 '/api/rooms/':()=>({rooms:[{room_id:1,room_number:'101',block:'A',available:1,capacity:2,occupied:1}]}),
 '/api/categories/':()=>({categories:[{category_id:1,category_name:'Electrical'}]})
};
const fetch=async(url)=>{const endpoint=url.split('?')[0];if(!fixtures[endpoint])throw Error('Unexpected endpoint '+endpoint);return {ok:true,status:200,json:async()=>fixtures[endpoint]()};};
class FakeFormData{constructor(form){this.form=form;this.entries=()=>Object.entries(form.values||{})}}
const context={document:doc,sessionStorage:storage,console,fetch,setTimeout,clearTimeout,URL,FormData:FakeFormData,window:{open(){}},Intl,URLSearchParams};
vm.createContext(context);vm.runInContext(js,context);
async function tick(){await new Promise(r=>setTimeout(r,12));}
(async()=>{
 await tick();assert.match(root.innerHTML,/Sign in to your workspace/);
 const submit=events.submit;
 const button={disabled:false,isConnected:true};
 await submit({target:{id:'authForm',values:{username:'warden',password:'secret'},querySelector:()=>button},preventDefault(){}});
 await tick();assert.match(root.innerHTML,/Welcome back, warden/);
 assert.match(root.innerHTML,/Oracle connected/);
 assert.match(root.innerHTML,/Maintenance team/);
 const click=events.click;
 await click({target:{dataset:{action:'navigate',view:'complaints'},closest(){return this;}}});
 await tick();assert.match(root.innerHTML,/Socket &lt;sparking&gt;/); // HTML-escaped title
 await click({target:{dataset:{action:'detail',id:'1003'},closest(){return this;}}});
 await tick();assert.match(root.innerHTML,/Complaint #1003/);
 await click({target:{dataset:{action:'navigate',view:'staff'},closest(){return this;}}});
 await tick();assert.match(root.innerHTML,/Ravi/);
 console.log('PASS: unauthenticated login, API state, navigation, role dashboard, complaint detail, escaping and staff listing');
})().catch(e=>{console.error(e);process.exitCode=1});
