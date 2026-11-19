export function displayMember(profile,identities={}){
 if(!profile)return profile;
 const saved=identities[profile.id]||{};
 return {...profile,source_name:profile.source_name||profile.name,name:saved.nickname||profile.name,avatar:saved.avatar||''};
}
export const displayRoles=(roles,identities={})=>Object.fromEntries(Object.entries(roles||{}).map(([seat,p])=>[seat,displayMember(p,identities)]));
