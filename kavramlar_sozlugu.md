# DEFTERIKI — Kavramlar Sözlüğü

## Amaç

Bu sözlük, DEFTERIKI projesinde geçen kavramların tek ve ortak tanımını tutar. Aynı kavramı proje sahibi (Abdüllatif), kodu yazan ajan (Claude Code) ve Cowork'un aynı anlamda kullanmasını sağlamak için vardır. Bir kavram burada nasıl tanımlandıysa kodda, dokümanlarda ve sohbetlerde o anlamda kullanılır; farklı bir anlam gerekiyorsa önce bu sözlük güncellenir.

**Kural:** Sözlüğe kavram ekleme, mevcut bir tanımı değiştirme veya silme yalnızca Abdüllatif'in onayıyla yapılır. Ajanlar (Claude Code, Cowork) onaysız ekleme yapamaz.

## Kavramlar

### Nesne

Dış dünyadaki bir varlığın yapılandırılarak DEFTERIKI'ye kaydedilmesiyle nesne olur. Yapılandırmaya uğramayan şeyler nesne değildir; belgenin kendisi (PDF, fotoğraf) nesne değildir. Finansal hareketler nesne değildir; bire bir işlenir ve nesnelere bağlı, kendi işlem kurallarıyla tutulan kayıtlardır.

Her nesnenin benzersiz kimliği ve Cowork'un belirlediği serbest özellikleri vardır. Nesneler seviyeli bir hiyerarşide durur: seviye 0 hiçbir üst nesneye bağlı değildir; diğer nesneler hemen önceki seviyedeki en az bir nesneye bağlıdır; seviye atlanamaz; bir nesne birden fazla üst nesneye bağlanabilir. Sistem nesnenin banka, hesap ya da fiş olduğunu yorumlamaz; bağlantıları ve seviye kurallarını denetler.

_(Abdüllatif'in onayıyla eklendi, 2026-09-11.)_
