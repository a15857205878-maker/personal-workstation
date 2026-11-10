const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');
const fn=html.match(/function presentationPhoto\(file,collaboration\)\{[^\n]+\}/)[0];
test('photo routing uses attachment input context, including the shared conversation dialog',()=>{
 const context={format:'pptx'};context.$=id=>{assert.equal(id,'collabOutput');return {value:context.format};};vm.createContext(context);vm.runInContext(fn,context);
 assert.equal(context.presentationPhoto({name:'garden.PNG'},true),true);
 assert.equal(context.presentationPhoto({name:'garden.png'},false),false);
 assert.equal(context.presentationPhoto({name:'notes.txt'},true),false);
 context.format='docx';assert.equal(context.presentationPhoto({name:'garden.png'},true),false);
});
